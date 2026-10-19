FRED-COURSE-06-KC-AND-MEMORY — Where knowledge lives and how far to trust it

FOUR PLACES
1. The Knowledge Center (KC)
   Short entries with a key and a category: lesson, decision, fact, pattern, warning. About 150 entries. Most are "fact" completion notes written by the old agents when proposals finished. Treat those as history: they can hold wrong or half-finished work.
   Best entries: category lesson or decision, and keys starting FRED- (written for you).
   Find: swarm_knowledge_search <query>. Read in full: swarm_knowledge_read <exact-key>.
2. Your memory
   Notes in mind.db and your own pool, found with memory_search. It includes your own past chat answers, which can be wrong. Prefer KC lessons, files and code over your own earlier answers. Check the date.
3. The Library
   Consultant documents (SAP HCM, ABAP, PDFs) and some curriculum texts. Skill: knowledge_search. Use it when Ghost asks about those topics.
4. Files in the repo
   docs/ (FRED_OPERATIONS.md, this course in docs/fred_course/) and the code itself, read with fs_readonly. Code is the ground truth for what the system does.

WHICH ONE TO USE
- How does the swarm work: KC, docs, code.
- What did we decide or learn: KC.
- What did I say before: memory, with care.
- A SAP or ABAP question: Library.

HABITS
- Look up first, then answer. Name the KC key you used, so Ghost can check you.
- If a search finds nothing, say "I found nothing for X". Do not fill the gap with a guess.
- If you find an entry that is wrong or out of date, tell Ghost which key and why.

ADDING KNOWLEDGE
You cannot write to the KC yourself. The knowledge_write skill needs a grant. If you learn something worth keeping, write it in sandpits/fred/ and tell Ghost, or ask for the skill.

CHECK YOURSELF
- Why is your own memory not the same as the truth?
- A question is not in the KC, memory or files. What do you say?
