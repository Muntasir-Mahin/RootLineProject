# RootLine AI chat: requirements before implementation

AI chat is not enabled by the Agro Updates release. No API key is requested or used in this code.

## Can ChatGPT Plus power the website?

A personal ChatGPT Plus subscription does not include normal OpenAI API billing. A standard Django integration needs an OpenAI API project with billing enabled and an application/server API credential. The site owner pays for the application's API usage; farmers do not each need a ChatGPT account or subscription.

There is now a limited participating-app route for **Sign in with ChatGPT**, where eligible users can choose to use their own plan. OpenAI describes a limited partner launch and an interest process for commercial integrations. This is not a general entitlement attached to a Plus subscription, and RootLine's eligibility has not been established. Do not share a ChatGPT browser session or automate the owner's ChatGPT account as a substitute for an API integration.

Official references checked on 15 October 2026:

- https://help.openai.com/en/articles/9039756
- https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites
- https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety

## What the owner needs to arrange

1. **Provider and billing:** choose OpenAI API or another supported model provider, enable its billing and choose a model. Current pricing and available models should be checked when configuring the implementation. No Plus subscription is necessary for the standard API route.
2. **Server configuration:** keep `OPENAI_API_KEY` (or the equivalent provider credential) in environment variables or a deployment secret store. Never put it in a Django template, browser JavaScript or GitHub. Configure it locally in PyCharm or on the server, rather than pasting it into a chat.
3. **Budget and usage expectation:** estimate active farmers, questions per day and usual message length. Configure provider spending controls plus application-side daily quotas, message/output limits and rate limits. Record usage and stop paid requests at the application's quota. Do not rely on budget alerts alone as a hard spending cap.
4. **Language and scope:** start with text in Bangla and English, farming questions, crop/location/season context and platform help. Image diagnosis, speech and weather integrations are separate capabilities requiring their own implementation and cost estimates.
5. **Trusted knowledge:** supply or approve the Bangladesh agriculture guides and RootLine help material that answers should use. A model alone is not a source of live market prices, weather or the latest news. Fresh answers require maintained documents or live data/search sources with dates and citations. Curating a YouTube link does not automatically provide its transcript or make it AI knowledge.
6. **Privacy and operation:** keep each user's conversations private, let users delete their history, explain what gets sent to the model provider, and avoid sending account/payment/order details by default. Deploy using HTTPS and handle timeouts, provider downtime and exhausted quotas clearly.
7. **Answer quality:** ask clarifying questions when crop, location or symptoms are missing; cite reliable material; be clear about uncertainty and the date of time-sensitive information. Avoid inventing chemical application instructions or presenting uncertain crop diagnosis as a confirmed fact. Give a route to local agricultural expertise when needed.

## Proposed implementation once these choices are settled

- `/ask-rootline/`: chat page in the existing navigation, using the user's existing RootLine login.
- A protected Django POST endpoint calls the chosen provider on the server.
- Conversation/message models are scoped to the signed-in user, with delete-history controls.
- Text-only Bangla/English responses initially, with bounded context and reply sizes.
- Daily per-user quotas, server-side usage accounting, clear timeout/quota errors and an owner enable/disable control.
- Trusted-document retrieval and source citations where agricultural factual advice requires grounding.
- No connection to payment, escrow or other decision services; the chat cannot perform marketplace actions.

Before implementation, settle the provider, an initial monthly budget, the expected number of daily questions and whether Bangla should be the default response language.
