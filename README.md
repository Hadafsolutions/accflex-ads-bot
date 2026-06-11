# AccFlex Google Ads Bot   
  
Automated Google Ads management and daily reporting bot for AccFlex (KSA campaigns).

## What it does on startup
1. Adds negative keywords (competitors + irrelevant terms) to KSA (May) #2
2. Enables the "Accounting" ad group
3. Sends confirmation to Discord

## Daily (every morning at 9 AM)
- Pulls yesterday's performance for all campaigns
- Sends report to Discord with spend, clicks, conversions, CPA
- Alerts on campaigns with high spend + zero conversions

---

## Deploy on Railway

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "AccFlex Ads Bot"
git remote add origin https://github.com/YOUR_USERNAME/accflex-ads-bot.git
git push -u origin main
```

### Step 2: Create Railway Project
1. Go to railway.app
2. Click "New Project" → "Deploy from GitHub repo"
3. Select `accflex-ads-bot`
4. Railway will auto-detect Python

### Step 3: Set Environment Variables
In Railway → your project → Variables, add:

| Variable | Value |
|---|---|
| GOOGLE_ADS_DEVELOPER_TOKEN | F4Z7pp-pIIZAqdJGQ0dv5w |
| GOOGLE_ADS_CLIENT_ID | 863383181160-... |
| GOOGLE_ADS_CLIENT_SECRET | GOCSPX-... |
| GOOGLE_ADS_REFRESH_TOKEN | 1//03CMPnB... |
| GOOGLE_ADS_CUSTOMER_ID | 8823799088 |
| GOOGLE_ADS_LOGIN_CUSTOMER_ID | YOUR_MCC_ID |
| DISCORD_WEBHOOK_URL | https://discord.com/api/webhooks/... |
| REPORT_HOUR | 9 |

### Step 4: Get Discord Webhook
1. Open Discord → your server → any channel
2. Click ⚙️ Edit Channel → Integrations → Webhooks
3. Create Webhook → Copy URL
4. Paste into DISCORD_WEBHOOK_URL variable

### Step 5: Deploy
Railway auto-deploys on every git push.
Check logs in Railway → your service → Logs.

---

## MCC Account ID
Your Developer Token is under your Manager Account (MCC).
Find your MCC ID in Google Ads (top left account switcher — the parent account number).
