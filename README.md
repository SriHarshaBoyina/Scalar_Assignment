# 🧠 Scalar Assignment – Jira Issue Scraper (Hadoop Project)

## 📌 Overview
This project focuses on **scraping and processing Jira issues** from the **Apache Hadoop** project.  
It automates the collection, cleaning, and structuring of issue data to prepare it for downstream tasks such as **summarization** and **question–answer generation** using Large Language Models (LLMs).

---

## ⚙️ Features
- ✅ **Automated Jira Issue Scraping** — Collects issue metadata, descriptions, and comments.  
- 🧹 **Data Structuring** — Cleans and formats data into JSON format for easy analysis.  
- 💬 **Summarization & Q/A Generation** — Creates text prompts for each issue to aid understanding.  
- 💾 **Checkpointing Support** — Saves progress to resume scraping from the last checkpoint.  

---

## ⚠️ Note on Dataset Size
The complete raw dataset (`hadoop.jsonl`) contains **17,415 Jira issues**, resulting in a file size of approximately **75 MB**.  
Since GitHub restricts file uploads larger than **25 MB**, the full dataset could not be included in this repository.  
However:
- A smaller sample file `sample_hadoop.json` is provided for reference.  
- The complete dataset (`hadoop.jsonl.zip`) can be shared upon request or generated again using the provided scraper script.

---

## 🧰 Files in Repository
| File Name | Description |
|------------|--------------|
| **`jira_scraper.py`** | Main Python script for scraping and processing Jira issues. |
| **`requirements.txt`** | List of required Python libraries (e.g., `requests`, `tqdm`, `beautifulsoup4`, etc.). |
| **`sample_hadoop.json`** | Processed output file containing structured Hadoop issues with summaries and Q&A prompts. |
| **`checkpoint-HADOOP.json`** | Checkpoint file to resume scraping from the last completed issue. |
| **`hadoop.jsonl.zip`** | *(Large raw dataset, excluded from GitHub)* — contains the complete collection of 17,000+ Hadoop issues in JSON Lines format. |

---

## 🧩 Sample Output
Each entry in `sample_hadoop.json` includes:
```json
{
  "id": "12312573",
  "key": "HADOOP-8",
  "title": "NDFS DataNode advertises localhost as it's address",
  "status": "Closed",
  "priority": "Major",
  "description": "...",
  "comments": [...],
  "derived": {
    "summary_prompt": "Summarize the following Jira issue: ...",
    "qa_prompt": "Write 3 question-answer pairs that help understand this issue: ..."
  }
}
