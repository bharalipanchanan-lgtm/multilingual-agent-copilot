# Claviq Agent Copilot: Progress So Far

As of 2026-11-05. This file has two parts. Part 1 explains each step in plain English. Part 2 lists the technical components built in each step, in the same order.

---

## Part 1. The steps in plain English

**Step 1. Setting the goal.** We agreed to build a working demo of the Claviq Agent Copilot that runs on the laptop for free. An insurance agent asks a question about a health policy in English, Hindi or Hinglish, and the copilot answers from the policy document. It shows the exact clause and page, and says "not stated in the document" when the policy does not answer.

**Step 2. Teaching the system to read policies.** We wrote code that opens each policy PDF and cuts it into small pieces, keeping the page number on every piece. It also removes junk such as repeated headers, footers and the table of contents. The pieces are stored in a local search database, so the system can quickly find the parts of a policy that match a question.

**Step 3. Writing the answers.** A free AI model running on the Mac (Qwen) writes the answer, using only the pieces the search found. We added safety checks around it. Every number in the answer must appear in the quoted clause. If the evidence is weak, the system refuses rather than guesses. Questions the policy cannot answer, such as premiums, are turned away politely.

**Step 4. Building the chat screen.** We built a web page that looks like WhatsApp, plus a small server behind it. The answer appears word by word, with a clause card that links to the exact PDF page.

**Step 5. Measuring quality.** We wrote 20 test questions in three languages, including two trick questions, and checked that the right clauses are found and the answers are correct. Today the right clause is always found, and every question is answered or refused correctly.

**Step 6. The architecture document.** We wrote ARCHITECTURE.md to explain how the system is built, and it was merged into GitHub (PR #1).

**Step 7. Adding more policies.** Working from the handoff pack, we went from one policy to five: National Mediclaim, Oriental, United India, SBI and Royal Sundaram. Each new PDF had its own layout problems, such as broken headers, wide tables and separate columns for each plan, and we fixed the reader for each one. We also loaded the "fact table", a structured sheet used to compare policies side by side. A checker confirms that every quote in it really appears on the stated page. The fact values are still waiting for a human to verify them.

**Step 8. Fixing a dangerous mistake.** During testing the system said maternity was covered for SBI and United India, when those policies actually exclude it. We taught the system to recognise official exclusion clauses, and added a check that blocks any "covered" answer that rests only on an exclusion.

**Step 9. Choosing the policy by conversation.** We removed the dropdown. Now the copilot greets the agent with "Which policy document would you like to inspect? / Kaunsa policy document aapko dekhna hai?" The agent can type the name, tap a button or make a spelling mistake, and it still works. If a question arrives before a policy is chosen, the copilot holds the question and answers it once the policy is chosen. If the agent names an insurer we have not loaded, such as HDFC ERGO, the copilot says so instead of guessing.

**Step 10. Testing properly in a real browser.** The greeting was not visible at first. The cause was an old copy of the page saved in the browser, which we fixed. We then wrote an automated test that opens Chrome and clicks through the whole demo the way an agent would. It passes all 15 steps.

**Step 11. Adding voice.** We added a microphone button using Sarvam's speech to text service (Saaras). The agent speaks, the spoken words appear in the text box, the agent checks them and presses send. The Sarvam key lives only in the private .env file, which is never uploaded to GitHub. Typing still works if there is no internet.

**Step 12. Checking the Sarvam key.** We wrote one small script that makes a single call to Sarvam, to confirm the key works. It worked.

**Step 13. Real voice testing.** We played recorded questions into the page as if someone were speaking, with the real Sarvam service behind it. This found three problems, which we fixed. Sarvam rejected Chrome's audio format label. Sarvam spells "wali" as "vali". Hindi written in English letters was not linked to the English policy words. Now all four spoken questions pass from start to finish.

**Where things stand now.** The demo runs on the laptop with five policies, three languages, voice input and safety checks, and all tests pass. The work is saved on two GitHub branches that still need pull requests opened and merged. The remaining handoff tasks (4 to 10 and 12) have not started. Two things are still open before the CEO demo: a human needs to verify the fact table values, and a few known weak answers need work, such as Oriental ELITE maternity.

---

## Part 2. The technical components of each step

**Step 1. Setting the goal.** No code was written in this step. We fixed the stack: Python, FastAPI for the server, Chroma as the search database, bge-m3 for embeddings, and a plain HTML page. Everything had to run on the M1 Pro laptop. The rules and the plan are written down in [CLAUDE.md](CLAUDE.md), [PLAN.md](PLAN.md) and [PITCH.md](PITCH.md).

**Step 2. Reading the policies.** [parse.py](parse.py) reads each PDF with PyMuPDF and splits it into chunks of up to about 1,600 characters. Each chunk keeps its physical page, its printed page and the clause heading it sits under. Every policy has a row in [manifest.csv](data/policies/manifest.csv) with four settings:

| Setting | What it does |
|---|---|
| skip_pages | Leaves out the cover and the table of contents |
| page_offset | Converts the physical page number to the printed one |
| strip_regex | Removes repeated headers and footers |
| aliases | Lists the names an agent might call the policy |

[ingest.py](ingest.py) turns each chunk into a vector with bge-m3 and stores it in Chroma under data/chroma. [retrieve.py](retrieve.py) runs the search, with an optional filter by policy. [inspect_chunks.py](inspect_chunks.py) and [check_chunks.py](check_chunks.py) let a person review the chunks. They flag oversized chunks, leftover header or footer text and wrong page numbers.

**Step 3. Writing the answers.** [answer.py](answer.py) is the core of the system. It works in this order:

1. It decides what kind of question it has: one to answer from the policy, a comparison, or one outside the policy.
2. It fetches the top chunks, plus the chunks either side of them, because some clauses run onto the next page.
3. It builds a prompt with ten strict rules. Examples: answer only from the quoted text, and never work out amounts from a percentage.
4. It sends the prompt to the model.

[generate.py](generate.py) puts four interchangeable model backends behind one interface:

| Backend | What it is |
|---|---|
| mlx (default) | Qwen2.5 7B in 4 bit, run with Apple MLX, with a cache that skips re-reading the fixed part of the prompt |
| ollama | A local model run through Ollama |
| claude | The Claude API, optional and paid per use |
| extractive | No model; it quotes the best matching sentence |

After the model writes, three checks run:

- **Number check.** Every figure in the answer must appear in a cited chunk.
- **Citation repair.** Each clause and page reference must point to a chunk that was actually retrieved.
- **NOT_STATED sentinel.** If the model returns NOT_STATED, the reply becomes "Not stated in the document".

A refusal threshold on the search scores turns away questions with weak evidence.

**Step 4. The chat screen.** [server.py](server.py) is a FastAPI app. It streams each answer to the page piece by piece using Server-Sent Events (SSE). It also serves the PDFs, so a clause card can link straight to the right page (/pdf/{id}#page=N). [web/index.html](web/index.html) is one HTML file with plain JavaScript and no framework. [run_demo.sh](run_demo.sh) starts the server.

**Step 5. Measuring quality.** [eval/questions.yaml](eval/questions.yaml) holds 20 questions. The gold file in eval/gold records the correct clause and page for each one. Four scripts do the checking:

| Script | What it checks | Result now |
|---|---|---|
| [eval_retrieval.py](eval_retrieval.py) | Whether the right clause is found in the top 3 and top 6 results | 100% |
| [eval_answers.py](eval_answers.py) | Full answers: answered, refused or blocked, and response time | 17/17 answered, 3/3 refused, median about 5.7 s |
| [demo_check.py](demo_check.py) | The 11-step demo script, run against the live server | 11/11 |
| pytest in [tests/](tests/) | Unit tests | 217 passed, 1 marked as a known failure |

**Step 6. The architecture document.** [ARCHITECTURE.md](ARCHITECTURE.md) explains the design with mermaid diagrams. It covers the data flow, the API endpoints and the safety checks. It was committed on a branch, pushed and merged as PR #1.

**Step 7. More policies and the fact table.** The four new PDFs were renamed and added to the manifest. Each one exposed a parser problem, and each got its own fix in [parse.py](parse.py):

| Problem | Fix |
|---|---|
| Odd characters and spacing broke the header and footer patterns | Text is normalised (Unicode NFKC, collapsed spaces) before strip_regex runs |
| The rupee sign came out as a backtick | Backticks next to amounts are turned back into ₹ |
| Some table rows were far too long | split_row cuts them into smaller chunks |
| Numbers split across two lines | join_wrapped_numbers joins them again |
| Tables with one column per plan (PREMIUM, ELITE, ROYAL) | Each chunk is tagged with its plan, and the tags carry across pages |
| Text from the two halves of wide landscape pages got mixed up | Text is read in column order |
| Lines such as "5 Lakhs to 10 Lakhs" were taken for clause headings | The NOT_A_PART check rejects them |

For the fact table, [fact_table.py](fact_table.py) defines the format: one row per policy, plan and attribute, with 19 attributes, a status (stated, not_stated or unclear) and a supporting quote. [import_facts.py](import_facts.py) loads the handoff data into facts/*.json (86 rows) and exports a CSV for review. [compare.py](compare.py) builds comparison tables from it. [tests/test_fact_quotes.py](tests/test_fact_quotes.py) checks that each of the 135 quotes really appears on its stated page, after normalising quote marks and spaces.

**Step 8. The maternity safety fix.** [parse.py](parse.py) now spots IRDAI exclusion codes (for example "Code Excl 18") at the start of a clause and labels that chunk as an exclusion. [answer.py](answer.py) shows those chunks to the model with an EXCLUDED label. A polarity check (affirms_cover) blocks any answer that says something is covered when its only evidence is an exclusion. The agent sees "Draft blocked" instead. [tests/test_polarity.py](tests/test_polarity.py) covers this.

**Step 9. Choosing the policy by conversation.** [policy_select.py](policy_select.py) works out which policy the agent means. It matches the aliases from the manifest (including Hindi names), close spellings (using Python's difflib) and picks by number. It also recognises when a message only names a policy and asks nothing else. Insurers that are not loaded, such as HDFC ERGO, are recognised and politely refused.

[chat.py](chat.py) handles the conversation (the converse function):

- **Choosing and holding.** It asks which policy when none is chosen, and holds an early question to answer after the choice.
- **Language.** It remembers the agent's last language, so the reply stays in Hinglish after a tap.
- **Clean search.** Before searching, it removes the policy name from the question (strip_names) so the name does not skew the results.

The page lost its dropdown and gained a greeting with option buttons and a header chip that switches policy. [tests/test_policy_select.py](tests/test_policy_select.py) covers the matching.

**Step 10. Real browser testing.** The server now sends Cache-Control: no-store for the page, so the browser always loads the latest version. [tests/e2e_ui.py](tests/e2e_ui.py) uses Playwright to drive the installed Chrome through 15 demo steps. It checks what is actually on screen, fails on any console error or HTTP error, and saves a screenshot at each step.

**Step 11. Voice.** [stt.py](stt.py) sends the recording to Sarvam's speech-to-text endpoint using the saaras:v3 model in translit mode. In that mode, Hindi comes back written in English letters. The key is read from the SARVAM_API_KEY environment variable, and errors are turned into plain messages. [server.py](server.py) gained two endpoints: /api/voice reports whether voice is on, and /api/transcribe takes the uploaded audio. On the page, the browser's MediaRecorder captures up to 25 seconds from the microphone. The key sits in .env, which git ignores; [.env.example](.env.example) is a blank template. [tests/e2e_voice.py](tests/e2e_voice.py) tests the flow end to end against a stand-in Sarvam server ([mock_sarvam.py](tests/voice/mock_sarvam.py)), using Chromium's fake microphone to play recorded clips.

**Step 12. Checking the key.** [sarvam_hello.py](sarvam_hello.py) uses the official sarvamai SDK to make one chat call to sarvam-105b-conversations. It reads the key from .env and never prints it.

**Step 13. Real voice testing.** The test clips in [tests/voice/clips](tests/voice/clips) were made with the macOS say command in Indian English and Hindi voices. Two scripts use them with the real Sarvam service: [voice_check.py](voice_check.py) checks only the transcripts, and [tests/e2e_voice_real.py](tests/e2e_voice_real.py) runs the full path from microphone to answer. The three fixes were:

| Problem | Fix |
|---|---|
| Sarvam rejected Chrome's audio type, "audio/webm;codecs=opus" | media_type in [stt.py](stt.py) strips the codec part, and the stand-in server now enforces the same rule |
| "SBI vali policy" was not taken as choosing a policy | Sarvam's spellings ("vali", "chahie" and others) were added to the filler words in [policy_select.py](policy_select.py) and [chat.py](chat.py) |
| The Romanised Hindi question came back "not stated" | HINGLISH_TERMS in [answer.py](answer.py) adds English equivalents (for example pre-existing disease) to the search query |

The fixes were committed as 041d83e on the feature/conversational-policy-select branch and pushed.
