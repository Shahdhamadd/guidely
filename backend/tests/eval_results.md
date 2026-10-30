| Metric | Direct (24) | Reworded (8) | Multi-section (4) | All answerable (36) | Target |
|---|---|---|---|---|---|
| Retrieval@3 | 24/24 = 100% | 8/8 = 100% | 3/4 = 75% | 35/36 = 97% | >= 80% |
| Answer correct | 23/24 = 96% | 7/8 = 88% | 3/4 = 75% | 33/36 = 92% | - |
| Reference coverage | 24/24 = 100% | 7/8 = 88% | 4/4 = 100% | 35/36 = 97% | >= 90% |
| Source precision | 22/24 = 92% | 6/8 = 75% | 4/4 = 100% | 32/36 = 89% | >= 80% |

Unanswerable questions refused correctly: 6/6 = 100%

## Misses

- [direct] Until when can I use leave days carried over from last year? -> failed: snippet_supports. Answer: You can use up to 5 unused leave days carried over from the last year before 31 March of the current year [1].
- [direct] When do I have to submit my expense receipts? -> failed: correct_answer, snippet_supports. Answer: Every expense needs a photo of the receipt. [1]
- [reworded] Am I allowed to keep client information on a thumb drive? -> failed: snippet_supports. Answer: No, you are not allowed to keep client information on a thumb drive [1].
- [reworded] Can I log in from home during my second week at the company? -> failed: correct_answer, correct_reference, snippet_supports. Answer: According to [3], during the first week, you will get access to Slack, but it's not specified if you can log in from home during the second week. However, it's mentioned that employees must be reachable on Slack during core hours when working remotely, which implies that you should be available on Slack during core hours, but it doesn't explicitly state that you can log in from home.
- [multi] Do I need a medical certificate for 3 sick days, and how much can I claim for home internet? -> failed: retrieved, correct_answer. Answer: For 3 sick days, yes, you need a medical certificate [1]. 

I couldn't find information on claiming for home internet in the provided sources.
