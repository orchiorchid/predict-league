# 🚀 Deployment Guide: Prediction League Service

This service is a standard lightweight Python FastAPI application. It can be deployed in minutes on any modern cloud hosting platform (Render, Railway, Fly.io) or any Linux VPS using Docker or Systemd.

---

## 📋 Preparation: Push to GitHub

Most cloud platforms (Render, Railway, Fly) deploy directly from a Git repository:

```bash
# Initialize git (if not already done)
git init
git add .
git commit -m "Initial commit of Prediction League service"

# Push to your GitHub repository
git remote add origin https://github.com/<your-username>/prediction-league.git
git branch -M main
git push -u origin main
```

---

## Option 1: Render.com (Recommended — Easiest & Free/Low Cost)

Render is one of the easiest platforms to deploy FastAPI apps with free SSL and automatic redeploys on `git push`.

### Steps:
1. Sign up / Log in at [render.com](https://render.com).
2. Click **New +** in the top right and select **Web Service**.
3. Connect your GitHub repository (`prediction-league`).
4. Configure the service:
   - **Name**: `prediction-league` (or any name you like)
   - **Region**: Choose the closest region (e.g. Frankfurt or Oregon)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn backend.main:app --host 0.0.0.0 --port $PORT
     ```
5. In **Environment Variables**, add:
   - Key: `SPREADSHEET_ID`
   - Value: `1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4`
6. Click **Create Web Service**.
7. Render will build and deploy your app. Within 1–2 minutes, you will get a live public URL (e.g. `https://prediction-league.onrender.com`).

---

## Option 2: Railway.app (Ultra Fast 1-Click Deploy)

Railway automatically detects either your `Dockerfile` or `requirements.txt`.

### Steps:
1. Sign up at [railway.app](https://railway.app).
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select your repository.
4. Railway will automatically build the image using the provided [Dockerfile](Dockerfile).
5. In **Variables**, add:
   - `SPREADSHEET_ID`: `1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4`
6. In **Settings** → **Networking**, click **Generate Domain** to get a public HTTPS link (e.g. `https://prediction-league-production.up.railway.app`).

---

## Option 3: Fly.io (Command Line Deployment)

Fly.io runs Docker containers close to your users.

### Steps:
1. Install flyctl:
   - Windows PowerShell: `iwr https://fly.io/install.ps1 -useb | iex`
   - macOS / Linux: `curl -L https://fly.io/install.sh | sh`
2. Log in:
   ```bash
   fly auth login
   ```
3. Initialize and launch:
   ```bash
   fly launch --name prediction-league
   ```
   Fly.io will automatically read your `Dockerfile`.
4. Deploy:
   ```bash
   fly deploy
   ```

---

## Option 4: Deploying on a VPS (Ubuntu / Debian) using Docker

If you have your own VPS (DigitalOcean, Hetzner, AWS EC2, Linode, Timeweb, etc.):

### 1. Install Docker and Docker Compose on your server:
```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker
```

### 2. Clone your repository:
```bash
git clone https://github.com/<your-username>/prediction-league.git
cd prediction-league
```

### 3. Launch with Docker Compose:
```bash
docker-compose up -d --build
```
The app will be running in the background on port `8000`.

### 4. Optional: Setup Nginx Reverse Proxy with SSL (Certbot)

Create an Nginx configuration `/etc/nginx/sites-available/prediction.conf`:

```nginx
server {
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site and get free SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/prediction.conf /etc/nginx/sites-enabled/
sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com
```

---

## Option 5: Deploying on a VPS with Systemd (Without Docker)

If you prefer running directly with Python and systemd:

### 1. Setup virtual environment:
```bash
cd /opt/prediction-league
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create Systemd service `/etc/systemd/system/prediction.service`:
```ini
[Unit]
Description=Prediction League FastAPI Service
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/prediction-league
Environment="SPREADSHEET_ID=1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4"
ExecStart=/opt/prediction-league/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now prediction
```

---

## 🔒 Summary of Environment Variables

| Variable | Default Value | Description |
|---|---|---|
| `SPREADSHEET_ID` | `1oibdWWMrTXoFXozDIo4jfcukfNNJOfMbrTduzDS0Ji4` | ID of the Google Sheet to extract predictions from |
| `PORT` | `8000` | Port for the HTTP server |
