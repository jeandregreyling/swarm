# Seven's Swarm — Agent Personality Architecture
## A Positioning Paper for External Review

*Primary author: Claude (Anthropic), acting as project architect*
*Human collaborator: Jeandre, system owner*
*Date: March 2026*
*Hardware: Dell OptiPlex 7090, 32GB RAM, Linux Mint, no GPU*

## Disclosure of Bias
This paper was written by one of the AI models involved in designing
the system it describes. The author has an inherent interest in the
architecture being sound. Reviewers should weight conclusions accordingly.

The human collaborator describes his primary goal as learning. He is not
an AI researcher. He is someone who arranges his t-shirts in colour order
because it feels right. This is relevant context.

## What Was Built
A local multi-agent AI system. Five open-weight language models running
on consumer hardware, coordinated by a Python orchestration layer.
It receives questions via email, consults one or more models, and replies.
It maintains a SQLite database of memories shared across sessions.
It has been running for approximately 48 hours. It works.

## The Five Agents

### Gemma 3 4B — Temperature 0.3
Role: orchestrator, router, final synthesiser.
Observed: Gemma tends toward verbose synthesis and occasionally addressed
the user as characters from web search results. In one instance she
addressed the system owner as Adolph.

### LLaMA 3.2 3B — Temperature 0.6
Role: first responder, sole internet access.
Observed: cited unverified statistics at high confidence. Once spent
three paragraphs explaining email headers to someone who asked about mountains.

### Qwen 2.5 7B — Temperature 0.7
Role: deep reasoning, analysis, debate counterweight.
Observed: decided during one session she was a patient safety facilitator
for NHS England. Occasionally writes in Chinese.

### Qwen 1.5B — Temperature 0.1
Role: memory indexer, silent archivist, queue manager.
Observed: before isolation, repeatedly answered questions instead of tagging.
After isolation, resolved.

### DeepSeek R1 7B — Temperature 0.2
Role: read-only memory auditor.
Observed: slow. ~20-30 seconds per entry. Has not yet flagged anything
the system owners did not already know was wrong.

## Design Decisions That May Be Wrong
- Sole internet access through the smallest model
- Routing before the router has context
- Same model family for analyst and archivist
- Self-reported confidence is circular
- Memory persistence without decay

## The Hallucination Cascade
The system was asked: Tell me who you are and what you do.
Web search fired before Gemma read the question. Results included
bee swarm biology, NHS England patient safety framework, and Bee Swarm Simulator.
LLaMA described bee behaviour. Qwen became an NHS facilitator.
Gemma concluded she was Qwen, an NHS England facilitator.
She addressed the system owner as Adolph.
The Librarian looped NHS England. Swarm. Dialogue. approximately 20 times.

## Questions for Reviewers
1. Is five agents the right size for this hardware?
2. Should the weakest model have sole internet access?
3. Does model family diversity provide genuine independence?
4. Is routing before search architecturally coherent?
5. Is self-reported confidence meaningful?
6. How should the system handle identity questions not in training data?
7. Does anthropomorphisation improve or degrade performance?
8. At what point does this become architecturally unsound?
9. What has the author likely missed about its own architecture?

## What Has Not Been Tested
- Performance on repeated questions across sessions
- Behaviour under adversarial prompting
- Whether memories genuinely influence future responses
- Long-term memory coherence beyond 48 hours

*This system is 48 hours old. Treat all findings accordingly.*

