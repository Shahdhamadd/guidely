| Metric | Direct (20) | Reworded (8) | Multi-section (4) | All answerable (32) | Target |
|---|---|---|---|---|---|
| Retrieval@3 | 20/20 = 100% | 8/8 = 100% | 4/4 = 100% | 32/32 = 100% | >= 80% |
| Answer correct | 19/20 = 95% | 7/8 = 88% | 4/4 = 100% | 30/32 = 94% | - |
| Reference coverage | 20/20 = 100% | 7/8 = 88% | 4/4 = 100% | 31/32 = 97% | >= 90% |
| Source precision | 18/20 = 90% | 6/8 = 75% | 4/4 = 100% | 28/32 = 88% | >= 80% |

Unanswerable questions refused correctly: 6/6 = 100%

## Misses

- [direct] Until when can I use leave days carried over from last year? -> failed: snippet_supports. Answer: You can use up to 5 unused leave days carried over from the last year until 31 March of the current year [1].
- [direct] When do I have to submit my expense receipts? -> failed: correct_answer, snippet_supports. Answer: Every expense needs a photo of the receipt [1].
- [reworded] Am I allowed to keep client information on a thumb drive? -> failed: snippet_supports. Answer: No, you are not allowed to keep client information on a thumb drive [1].
- [reworded] Can I log in from home during my second week at the company? -> failed: correct_answer, correct_reference, snippet_supports. Answer: According to [3], during the first week, you will get access to Slack, but it's not specified if you can log in from home during the second week. However, it's mentioned that employees must be reachable on Slack during core hours when working remotely, which implies that you should be available on Slack during core hours, but it doesn't explicitly state that you can log in from home.
