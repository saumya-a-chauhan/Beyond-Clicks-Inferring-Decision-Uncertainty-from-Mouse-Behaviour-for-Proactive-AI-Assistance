# Deploying the study website (so it works from any laptop)

The site needs two free services:

- **Neon** for the database (Postgres), so data survives restarts and all laptops write to the same place.
- **Render** to run the website.

GitHub Pages hosts the public project page (`docs/index.html`).

Total time: about 20 minutes, done once.

## 1. Database: Neon

1. Go to https://neon.tech and sign up (free).
2. Create a project, for example `hti-study`, in a region near India (for example Singapore).
3. On the project dashboard, copy the **connection string**. It looks like
   `postgresql://user:password@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
   Keep it secret: it gives full access to the data.

The tables are created automatically the first time the website starts.

## 2. Website: Render

1. Go to https://render.com and sign up with your GitHub account.
2. **New → Blueprint**, then pick the repository
   `saumya-a-chauhan/Beyond-Clicks-Inferring-Decision-Uncertainty-from-Mouse-Behaviour-for-Proactive-AI-Assistance`.
   Render reads `render.yaml` and proposes one web service.
3. Fill in the secret values when asked:

   | Key | Value |
   | --- | --- |
   | DATABASE_URL | the Neon connection string |
   | ADMIN_PASSWORD | a long password for the researcher dashboard (share it only with the team) |
   | GEMINI_API_KEY | your Gemini key |
   | GROQ_API_KEY | your Groq key |

   `SECRET_KEY` is generated automatically.
4. Click **Apply**. The first build takes a few minutes. Your study URL is shown at the top, for example
   `https://beyond-clicks-study.onrender.com`.
5. Open `<URL>/admin`, log in, and run **Export & tools → Check the AI providers**.

Notes:

- On the free plan the server sleeps after about 15 minutes without visitors, and the first visit then takes about
  50 s. Open the site about 2 minutes before a participant arrives.
- To change a key later: Render → your service → **Environment** → edit → **Save**. The service restarts.
- Every push to the `main` branch on GitHub redeploys the site automatically. **Do not push code changes during the
  main study**, except for critical fixes, and write any fix down.

## 3. Project page: GitHub Pages

1. On GitHub: repository → **Settings → Pages**.
2. Source: **Deploy from a branch**. Branch: `main`. Folder: `/docs`. Save.
3. After a minute the page is at
   `https://saumya-a-chauhan.github.io/Beyond-Clicks-Inferring-Decision-Uncertainty-from-Mouse-Behaviour-for-Proactive-AI-Assistance/`.
4. Edit `docs/index.html` to add the team names, the presentation PDF (put it in `docs/`) and the video link.

The project page is public; the study data is not (it is only behind the dashboard password).

## Running locally instead

Leave `DATABASE_URL` empty in `.env` and the site uses a file `hti_study.db` in the project folder:

```bash
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

## Security checklist

- `.env` is in `.gitignore`. Never commit keys or the password.
- API keys that were shared in chat or messages should be **rotated** (create new ones, delete the old ones) before
  the real study.
- Only the researcher dashboard can read or export data. Participants only send their own answers, using a random
  session token kept in their browser and sent in a request header, never in the URL.
