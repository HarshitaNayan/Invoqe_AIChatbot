# Hynex — AI Learning Assistant

Hynex is a web-based learning assistant built with FastAPI and the Gemini API. It combines conversational answers with file summaries, quizzes, flashcards and tools for organising study chats.

Created by **Harshita Nayan** as part of the **Invoqe AI/ML Developer internship — AI Chatbot & NLP System**.

**[Live Demo](https://invoqe-aichatbot.onrender.com/)** · **[GitHub Repository](https://github.com/HarshitaNayan/Invoqe_AIChatbot)**

## Preview

### Chat interface and message controls

![Hynex chat interface with collapsible sidebar, message actions and learning tools](screenshots/hynex-interface.png)

| Control | What it does |
| --- | --- |
| Sidebar menu / close arrow | Collapse or reopen the sidebar to change the available chat space. |
| New chat | Start a separate conversation. |
| Pinned / Chats | Find pinned conversations and other saved chats. |
| Copy | Copy the full text of your message or a Hynex reply. Code blocks also have their own copy control. |
| Edit | Change one of your messages and send it again to generate a new reply. |
| Retry | Request another response to the question associated with a Hynex reply. |
| Review answer / Review | Give feedback or compare answer wording with reference text. |
| Sources | Open the knowledge-search panel to inspect relevant retrieved excerpts. |
| API key | Add or remove your own Gemini API key for the current tab. |
| Appearance | Switch light/dark mode and choose an accent colour. |
| Account | Register, sign in or sign out; Google sign-in is available when configured. |
| Knowledge | Search bundled learning notes and selected text attachments. |
| Quiz / flashcards | Generate multiple-choice quizzes or revision cards. |
| Files | Manage uploaded files, select attachments or request summaries. |
| Plus button | Attach supported documents or images. |
| Microphone | Dictate a message using browser speech recognition, then review and send it. |
| Message box / send arrow | Type or paste a question and send it. Enter sends; Shift+Enter adds a new line. |
| Guest status | Indicates that guest chats are saved in the current browser. |

Editing or retrying a turn replaces its subsequent conversation history. When later turns would be removed, the app asks for confirmation. Retry requires a working Gemini connection and uses the chat's currently selected attachments.

### Pin, rename and delete chats

![Hynex sidebar showing rename, pin and delete controls](screenshots/hynex-chat-controls.png)

Hover over a chat in the sidebar to reveal its controls (also exposed on touch devices):

- **Rename:** use the pencil icon to change the conversation title.
- **Pin / unpin:** keep a conversation in the Pinned section or return it to the regular chat list.
- **Delete:** remove a conversation after confirming the deletion.

## Features

- **Bring your own key (BYOK):** each visitor supplies a Gemini key through **API key** or the Account panel. The key remains in page memory, clears on reload or sign-out, and is forwarded through the backend to Google for that visitor's AI requests. It is not saved in the database or browser storage. The app does not use a shared deployer key. Only enter keys on an app host you trust.
- **AI chat:** streamed Gemini responses, recent conversation context, Markdown formatting and copyable code blocks.
- **Collapsible sidebar:** open or close the conversation sidebar on desktop and mobile.
- **Message actions:** copy user messages and assistant replies, edit and resend questions, or retry a reply.
- **Chat management:** create separate chats, rename them, pin favourites and delete with confirmation.
- **Paste support:** paste plain text into the composer with Ctrl+V or the browser's Paste option. Clipboard images are attached through the existing upload system when the browser exposes an image file.
- **File attachments and summaries:** attach PDFs, UTF-8 TXT/Markdown notes and PNG/JPG/WEBP images. Ask questions about selected attachments or request a summary through **Files**. Supports up to six selected attachments per request and files up to the app's 5 MB limit.
- **Voice input:** dictate, review the recognised text, then send. Requires microphone permission and browser speech-recognition support.
- **Quizzes and flashcards:** generate multiple-choice questions with grading and explanations, or front/back cards for revision.
- **Appearance:** light and dark modes with selectable accent colours.
- **Accounts and saved chats:** local username/password accounts, server-side account chat storage and synchronisation. Guests retain conversations in their browser. Account chat copies may also be cached locally.
- **Google sign-in:** optional OpenID Connect login after OAuth configuration. Google handles its own account and password entry.
- **Access control:** backend ownership checks for private account data and uploads, plus an optional site-wide login requirement.
- **Knowledge retrieval:** search local notes and selected uploaded text using TF-IDF and LSA similarity. Retrieved excerpts can be inspected; Sources runs retrieval for the question rather than proving which sources the model used.
- **Answer review:** save human feedback and compare an answer with reference text using token overlap. The score measures wording similarity, not factual accuracy.
- **Offline fallback:** a local TF-IDF intent matcher provides limited prepared replies when Gemini is unavailable.
- **Creator identity:** direct creator questions identify Harshita Nayan. Google supplies the underlying Gemini model.

## How it works

1. Enter your Gemini key using **API key → Use key for this tab**.
2. Type, paste or dictate a question, optionally selecting study files.
3. The backend retrieves relevant local notes and includes selected file content and recent chat history where applicable.
4. Gemini generates an answer that streams into the interface. If generation fails before any text is returned, chat can use its limited local intent matcher.
5. Copy, edit or retry messages, inspect retrieved notes, or use the study tools to summarise files and generate quizzes or flashcards.

## Tech stack

**Backend:** Python, FastAPI, Uvicorn, SQLite, scikit-learn, Gemini API, google-auth, pypdf and Pillow.

**Frontend:** HTML, CSS, JavaScript, browser storage and browser speech recognition.

## Run locally

Clone the repository and install dependencies:

```bash
git clone https://github.com/HarshitaNayan/Invoqe_AIChatbot.git
cd Invoqe_AIChatbot
python -m pip install -r requirements.txt
```

Configure an available model using `GEMINI_MODEL` in your environment or a local `.env` file. For example, to match the model configured for this project's deployment:

```dotenv
GEMINI_MODEL=gemini-3.5-flash-lite
```

The model must be available to your Google project. Setting a model in Render does not configure your local computer. An environment variable overrides the fallback model name in `app/llm.py`.

Start the development server:

```bash
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**. Click **API key**, paste your own Gemini key and select **Use key for this tab**. Re-enter it after refreshing or reopening the app. AI requests use your Google project's quota and any applicable billing. No shared Gemini key is required on the server.

For optional Google sign-in, follow [GOOGLE_SIGN_IN_SETUP.md](GOOGLE_SIGN_IN_SETUP.md). Gemini keys and Google OAuth credentials serve different purposes. Set `HYNEX_REQUIRE_LOGIN=1` if all users must sign in.

Keep `.env` and private `runtime/` data out of Git. Public hosting needs HTTPS; set `HYNEX_COOKIE_SECURE=1` for secure session cookies. Account data and uploads require persistent storage to survive server replacement or redeployment.

## Project files

| Location | Purpose |
| --- | --- |
| `app/main.py` | FastAPI application and chat endpoint |
| `app/llm.py` | Gemini requests and streamed responses |
| `app/chatbot.py`, `app/preprocess.py` | Local intent matching and text processing |
| `app/extensions.py` | Feature APIs and request checks |
| `app/retrieval.py` | Local knowledge retrieval |
| `app/uploads.py` | File validation and extraction |
| `app/storage.py`, `app/google_login.py` | Accounts, persistence and Google login |
| `app/identity.py`, `app/quality.py` | Creator responses and lexical answer comparison |
| `data/intents.json`, `data/knowledge/` | Local intents and study notes |
| `static/index.html` | Main interface and original chat logic |
| `static/features.js`, `static/features.css` | Learning tools, accounts, attachments and appearance |
| `static/chat-controls.js`, `static/chat-controls.css` | Sidebar toggle, message actions and clipboard handling |
| `tests/` | Automated backend tests |
| `screenshots/` | README preview images |

Run backend tests from the project root:

```bash
python -m unittest discover -s tests
```

## Limitations

- AI answers and generated quiz answers can be incorrect; check important information.
- Gemini-dependent features require a visitor key, model access, available quota and a network connection. Offline replies cover basic stored intents only and may be irrelevant.
- Voice input is speech-to-text, not a live voice conversation. Clipboard-image paste and microphone behaviour depend on browser support.
- Some PDFs contain no extractable text. The upload code can forward scanned PDFs for Gemini processing; interpretation depends on model support and access.
- Google sign-in needs OAuth configuration. Local accounts do not currently provide password recovery or email verification.
- LSA retrieval uses a local statistical representation, not a neural embedding service.
- Without persistent hosting storage, server-side accounts, uploads and saved chats can be lost on redeployment. Browser chat storage is separate and can be removed by clearing browser data.

## Author

[Harshita Nayan](https://github.com/HarshitaNayan)
