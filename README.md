# ethnicity

Utility scripts to mark the ethnicity of signup names via the OpenAI API.

## Setup

1. Create a virtual environment (optional) and install any dependencies you need (the helper script relies only on the Python standard library).
2. Copy `.env.example` to `.env` and fill in your OpenAI credentials:

```bash
cp .env.example .env
echo "OPENAI_API_KEY=sk-..." >> .env
```

Supported environment variables:

| Name | Description |
| --- | --- |
| `OPENAI_API_KEY` | **Required**. OpenAI API key with sufficient quota. |
| `OPENAI_MODEL` | Optional. Defaults to `gpt-4o-mini`. |
| `OPENAI_CA_BUNDLE` | Optional. Custom CA bundle for TLS verification (defaults to `/etc/ssl/cert.pem`). |

## Marking Ethnicity In a CSV

Run `mark_ethnicity.py` to annotate a CSV where the first column contains the signup’s name. The script inserts an `Ethnicity` column as the second column and writes the result to `<input>_with_ethnicity.csv` (or the path you specify).

```bash
python3 mark_ethnicity.py signups.csv
```

### Options

- `output_csv`: optional path for the annotated file.
- `--limit N`: process only the first `N` rows (useful for sampling before a full run).
- `--no-header`: set if your CSV does not have a header row.
- `--prompt-file <file>`: provide custom instructions that the model should follow.
- `--model <id>`: override the model per run.
- `--feedback-store path`: CSV that stores verified labels (defaults to `feedback.csv`).
- `--fewshot-count K`: how many verified examples to inject into the prompt (defaults to `5`).
- `--force-api`: ignore feedback matches and always hit the API (useful when you want to re-evaluate an existing name).

### Example

Input (`signups.csv`):

```
name,email
Rahul Sharma,rahul@example.com
Sakura Tanaka,sakura@example.com
```

Command:

```bash
python3 mark_ethnicity.py signups.csv
```

Output (`signups_with_ethnicity.csv`):

```
name,Ethnicity,email
Rahul Sharma,Indian,rahul@example.com
Sakura Tanaka,East Asian,sakura@example.com
```

Any rows beyond `--limit` (or rows with empty names) receive an empty/`Unknown` ethnicity, ensuring the CSV structure remains intact.

## Human Feedback & Continuous Improvement

The workflow supports a lightweight retrieval-augmented loop so the system “learns” from your corrections:

1. Review the generated CSV.
2. Record approved mappings via `record_feedback.py`. Each entry is written to `feedback.csv` (ignored by git).
3. Future runs of `mark_ethnicity.py` will:
   - Reuse exact matches from `feedback.csv` without another API call.
   - Pull up to `--fewshot-count` similar examples from the feedback store and append them to the prompt, guiding the model toward your taxonomy.

### Recording Feedback

Add a single correction:

```bash
python3 record_feedback.py --name "Rahul Sharma" --ethnicity "Indian"
```

Or import many at once from a CSV that contains `name,ethnicity[,notes]`:

```bash
python3 record_feedback.py --from-csv reviewed_rows.csv
```

These entries live in `feedback.csv`, which you can treat like a growing knowledge base. Because the script references the file on every run, the model effectively benefits from your prior decisions (RAG-style) without full fine-tuning. Use `--force-api` whenever you need to override an existing label and then record the new feedback entry.
