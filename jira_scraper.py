#!/usr/bin/env python3
"""
jira_scraper.py
Simple, resilient Jira Issue scraper for issues.apache.org (Apache Jira).
Produces one JSON object per line (JSONL) suitable for LLM datasets.

Usage:
    python jira_scraper.py --project HADOOP --out hadoop.jsonl

Notes:
- Uses Jira REST API /rest/api/2/search
- Handles pagination with startAt/maxResults
- Handles 429/5xx via exponential backoff + jitter
- Checkpointing: checkpoint-<project>.json keeps last startAt and processed issue keys
"""
import requests, time, json, argparse, os, sys, random
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from tqdm import tqdm

BASE = "https://issues.apache.org/jira/rest/api/2"
DEFAULT_MAX_RESULTS = 100  # server may cap; 100 is a conservative choice

# --- Utilities ---
def html_to_text(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n").strip()

def safe_parse_date(s):
    try:
        return dateparser.parse(s).isoformat()
    except Exception:
        return s

def backoff_sleep(attempt, base=1.0, cap=60.0):
    sleep = min(cap, base * (2 ** attempt))  # exponential
    # add jitter
    sleep = sleep * (0.5 + random.random() * 0.5)
    time.sleep(sleep)

# --- Checkpointing ---
def load_checkpoint(project):
    fname = f"checkpoint-{project}.json"
    if os.path.exists(fname):
        return json.load(open(fname, "r"))
    return {"startAt": 0, "processed": []}

def save_checkpoint(project, checkpoint):
    fname = f"checkpoint-{project}.json"
    with open(fname + ".tmp", "w") as f:
        json.dump(checkpoint, f)
    os.replace(fname + ".tmp", fname)

# --- API callers with retry/backoff ---
def jira_get(session, url, params=None, max_attempts=6):
    attempt = 0
    while True:
        try:
            r = session.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            # network error - backoff retry
            if attempt >= max_attempts:
                raise
            backoff_sleep(attempt)
            attempt += 1
            continue

        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                # malformed JSON
                if attempt >= max_attempts:
                    raise
                backoff_sleep(attempt)
                attempt += 1
                continue

        if r.status_code == 429:
            # rate-limited
            # look for Retry-After header
            ra = r.headers.get("Retry-After")
            if ra:
                try:
                    wait = int(ra)
                except:
                    wait = 60
                time.sleep(wait + 1)
            else:
                backoff_sleep(attempt)
            attempt += 1
            if attempt > max_attempts:
                r.raise_for_status()
            continue

        if 500 <= r.status_code < 600:
            # server error
            if attempt >= max_attempts:
                r.raise_for_status()
            backoff_sleep(attempt)
            attempt += 1
            continue

        # client error (4xx except 429) - can't recover
        r.raise_for_status()

# --- Main logic ---
def fetch_comments(session, issue_key):
    url = f"{BASE}/issue/{issue_key}/comment"
    data = jira_get(session, url)
    comments = []
    for c in data.get("comments", []):
        comments.append({
            "id": c.get("id"),
            "author": c.get("author", {}).get("displayName"),
            "created": safe_parse_date(c.get("created")),
            "body": html_to_text(c.get("body"))
        })
    return comments

def issue_to_record(issue, comments):
    fields = issue.get("fields", {})
    record = {
        "id": issue.get("id"),
        "key": issue.get("key"),
        "title": fields.get("summary"),
        "project": fields.get("project", {}).get("key"),
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        "status": fields.get("status", {}).get("name") if fields.get("status") else None,
        "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
        "labels": fields.get("labels") or [],
        "created": safe_parse_date(fields.get("created")),
        "updated": safe_parse_date(fields.get("updated")),
        "description": html_to_text(fields.get("description") or ""),
        "comments": comments,
    }
    # Derived fields (example): content for LLM, summarization prompt, QA seed
    all_text = record["title"] + "\n\n" + record["description"] + "\n\n" + "\n\n".join([c["body"] for c in comments])
    record["content"] = all_text.strip()
    # simple summarization prompt (you can replace with your LLM pipeline)
    record["derived"] = {
        "summary_prompt": f"Summarize the following Jira issue:\n\n{record['content']}",
        "qa_prompt": f"Write 3 question-answer pairs that help understand this issue:\n\n{record['content']}"
    }
    return record

def scrape_project(project, out_path, jql=None):
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "Apache-Jira-Scraper/1.0 (+https://github.com/yourname)"})
    checkpoint = load_checkpoint(project)
    startAt = checkpoint.get("startAt", 0)
    processed = set(checkpoint.get("processed", []))
    maxResults = DEFAULT_MAX_RESULTS

    # Basic JQL: project only if not specified
    if not jql:
        jql = f"project = {project} ORDER BY created ASC"

    # open output file in append mode
    out_tmp = out_path + ".tmp"
    out_f = open(out_tmp, "a", encoding="utf-8")

    total = None
    pbar = None

    while True:
        params = {"jql": jql, "startAt": startAt, "maxResults": maxResults, "fields": "summary,description,project,reporter,assignee,status,priority,labels,created,updated"}
        url = f"{BASE}/search"
        data = jira_get(session, url, params=params)
        if total is None:
            total = data.get("total", None)
            if total is not None:
                pbar = tqdm(total=total, desc=f"{project} issues")

        issues = data.get("issues", [])
        if not issues:
            # nothing left
            break

        for issue in issues:
            key = issue.get("key")
            if key in processed:
                # already done; skip
                if pbar: pbar.update(1)
                continue
            # fetch comments (separate call)
            comments = []
            try:
                comments = fetch_comments(session, key)
            except Exception as e:
                # if comments fail repeatedly, continue with issue (still useful)
                print(f"Warning: failed to fetch comments for {key}: {e}", file=sys.stderr)
            record = issue_to_record(issue, comments)
            # write JSONL
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_f.flush()
            processed.add(key)
            if pbar: pbar.update(1)

        # update checkpoint
        startAt += len(issues)
        checkpoint = {"startAt": startAt, "processed": list(processed)}
        save_checkpoint(project, checkpoint)

        # stop condition
        if total is not None and startAt >= total:
            break
        # very small sleep to be polite
        time.sleep(0.5)

    out_f.close()
    # atomic rename to final file
    if os.path.exists(out_path):
        os.replace(out_path, out_path + ".bak")
    os.replace(out_tmp, out_path)
    print(f"Finished scraping project {project}. Output: {out_path}")

# --- CLI ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="JIRA project key (e.g., HADOOP)")
    parser.add_argument("--out", required=True, help="Output JSONL file path")
    args = parser.parse_args()
    scrape_project(args.project, args.out)
