# Which skills this project shows, and for which roles

This table is meant for recruiters and hiring managers. Each row says what a role needs and where in the project to see it. Everything listed can be opened and checked.

**How it was built:** I acted as product owner and orchestrator, setting the goals, making the trade-off decisions and reviewing and testing the work, while an AI model (Claude) wrote the code under my direction. Directing AI tools to a professional standard is itself a skill, shown here by the test suite, the written rules and the change history.

## Marketing analytics and measurement roles
| What the role needs | Where to see it |
| --- | --- |
| Telling real results from platform claims | The Dashboard headline and the "two ways of counting" note |
| Understanding controlled tests and uncertainty | [docs/METHODOLOGY.md](METHODOLOGY.md), the confidence cards and quality checks under Sources |
| Planning the next test | The Research next page |
| Matching test and control markets fairly, with honest pass or fail checks | The control market match cards and `python/propensity_scm.py` |
| Finding where ad money buys sales that would have happened anyway | The Audience tiers section on the Dashboard |
| Explaining measurement to non specialists | [docs/GLOSSARY.md](GLOSSARY.md), the Advisory council |

## Analytics governance, risk and data quality roles
| What the role needs | Where to see it |
| --- | --- |
| Controls that protect data and people | [docs/PRIVACY_AND_GOVERNANCE.md](PRIVACY_AND_GOVERNANCE.md): personal data blocked, summary only prompts |
| Audit trails | The Sign-off desk and its tamper evident record |
| Policy as data, version history | Settings and guardrails, each saved as a new version |
| Data integrity | Checksummed original data and an automatic check in CI |

## Product management for data and AI products
| What the role needs | Where to see it |
| --- | --- |
| Starting from users and their decisions | Four viewing perspectives, the [voice guide](VOICE_GUIDE.md) |
| Prioritising and making trade-offs openly | The case study in the README |
| Writing clear requirements and documentation | The `docs/` folder, the [changelog](CHANGELOG.md) |
| Honest limits | The "what this is and is not" box in the README |

## Business strategy, operations and consulting roles
| What the role needs | Where to see it |
| --- | --- |
| Turning analysis into recommendations | The Strategy page: trade-offs, cost of waiting, who is affected |
| Change management | The change plan and implications worksheet |
| Not overclaiming | Blank worksheet fields where the system cannot know the number |

## AI enablement, AI operations and responsible AI roles
| What the role needs | Where to see it |
| --- | --- |
| Using AI safely with company data | The AI brief: privacy scan, aggregate only, answer checker |
| Designing AI access with limits | [docs/ARCHITECTURE_MCP.md](ARCHITECTURE_MCP.md): no approve or execute tool |
| Human in the loop | Every decision signed by a named person |
| Evaluating AI output | The answer checker and the memo number checks |

## Technical program and delivery roles
| What the role needs | Where to see it |
| --- | --- |
| Quality gates and repeatability | Nearly 500 automated tests, continuous integration, pinned dependencies |
| Shipping and operating | One command Docker setup, a public demo, deploy guide |
| Communicating status | Changelog and roadmap |

## What I am not claiming
The data is synthetic, the project has not been used by a real company, and I did not hand write the code. The project shows how I frame problems, set standards, direct the build and check the result.
