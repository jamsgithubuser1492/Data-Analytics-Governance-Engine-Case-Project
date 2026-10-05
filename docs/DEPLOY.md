# Putting the demo online

The public demo runs on **Streamlit Community Cloud**, which is free and redeploys whenever the `main` branch changes. Each visitor gets a private, throwaway copy of the sample data, uploads and settings are switched off, and nothing is saved.

## Steps (about 5 minutes)
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Choose **Create app**, then **Deploy a public app from GitHub**.
3. Repository: `jamsgithubuser1492/Data-Analytics-Governance-Engine-Case-Project`. Branch: `main`. Main file path: `app/app.py`.
4. Open **Advanced settings**. Choose Python **3.11**. In **Secrets**, paste: `MMGE_DEMO_MODE = "1"`
5. Click **Deploy**. The first start takes a minute or two.
6. Copy the app address (it ends in `.streamlit.app`). In `README.md`, replace `https://YOUR-APP-URL.streamlit.app` with it (it appears once, in the line that starts "Open the live demo") and commit.

## If something looks wrong
* The page says "app is sleeping": free apps sleep after inactivity. Click the wake up button; it takes about 30 seconds.
* An old version shows: open the app menu and choose **Reboot app**.

## Alternative: Hugging Face Spaces
Create a new Space, choose **Docker**, and point it at this repository. The included `Dockerfile` already sets demo mode and port 8501; set the Space's `app_port` to 8501.

## Run the same thing locally
`docker build -t mmge . && docker run -p 8501:8501 mmge`
