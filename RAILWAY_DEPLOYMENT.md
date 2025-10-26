# Railway Deployment Guide for Bolt AI

## Prerequisites

- Railway account (sign up at [railway.app](https://railway.app))
- GitHub account (optional but recommended)
- All API keys ready (OpenAI, Twilio, Supabase, Email service)

## Step 1: Prepare Your Repository

### Option A: Deploy from GitHub (Recommended)

1. **Create a GitHub repository:**
   ```bash
   # Initialize git if not already done
   git init

   # Add .gitignore to exclude sensitive files
   echo ".env" >> .gitignore
   echo "venv/" >> .gitignore
   echo "__pycache__/" >> .gitignore
   echo "*.pyc" >> .gitignore
   echo "backups/" >> .gitignore
   echo "/tmp/" >> .gitignore
   echo "keys/" >> .gitignore

   # Add and commit all files
   git add .
   git commit -m "Initial commit - Bolt AI phone system"

   # Push to GitHub
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git branch -M main
   git push -u origin main
   ```

### Option B: Deploy Directly

You can also deploy by connecting Railway directly to your local folder.

## Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click "New Project"
3. Choose "Deploy from GitHub repo" (if using GitHub) or "Empty Project"
4. Select your repository or create empty project
5. Railway will automatically detect your Python app

## Step 3: Configure Environment Variables

In your Railway project dashboard:

1. Click on your service
2. Go to "Variables" tab
3. Add ALL environment variables from your `.env` file:

### Required Variables:

```
OPENAI_API_KEY=sk-proj-your-key-here
TWILIO_ACCOUNT_SID=ACxxxx
TWILIO_AUTH_TOKEN=your-token
TWILIO_NUMBER=+1XXXXXXXXXX
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-key
RESEND_API_KEY=re_xxxx
FROM_EMAIL=noreply@yourdomain.com
REPLY_TO_EMAIL=support@yourdomain.com
```

### Optional Variables:

```
AGENT_NAME=Bolt
COMPANY_NAME=Bolt AI Group
PRODUCT_PITCH=Your pitch here
VOICE=echo
TEMPERATURE=0.8
OPENAI_MODEL=gpt-4o-mini
MONTHLY_PRICE=$199
MAX_CALL_DURATION=3600
```

**IMPORTANT:** Do NOT set `PORT` or `PUBLIC_BASE_URL` - Railway handles these automatically!

## Step 4: Deploy

1. Railway will automatically build and deploy your app
2. Wait for deployment to complete (usually 2-3 minutes)
3. Once deployed, Railway will show your public URL (something like: `https://your-app.up.railway.app`)

## Step 5: Get Your Railway URL

1. In Railway dashboard, click "Settings" tab
2. Scroll to "Domains" section
3. Click "Generate Domain" if not already generated
4. Copy your Railway URL (e.g., `https://bolt-ai-production.up.railway.app`)

## Step 6: Update Twilio Webhooks

1. Log into [Twilio Console](https://console.twilio.com)
2. Go to Phone Numbers → Manage → Active Numbers
3. Click your Twilio phone number
4. Scroll to "Voice Configuration"
5. Update the webhook URL:
   - **A CALL COMES IN:** `https://your-railway-url.up.railway.app/inbound`
   - HTTP POST
6. Scroll to "Call Status Changes"
7. Update the status callback URL:
   - **STATUS CALLBACK URL:** `https://your-railway-url.up.railway.app/status`
   - HTTP POST
8. Click "Save"

## Step 7: Test Your Deployment

1. Call your Twilio number
2. Bolt should answer and start the conversation
3. Check Railway logs in dashboard for any errors
4. Verify emails are being sent

## Monitoring & Logs

### View Logs:
1. In Railway dashboard, click on your service
2. Click "Deployments" tab
3. Click on the active deployment
4. View real-time logs

### Check Health:
Visit: `https://your-railway-url.up.railway.app/health`

Should return: `{"status":"ok"}`

## Updating Your App

### If using GitHub:
```bash
# Make changes to your code
git add .
git commit -m "Description of changes"
git push

# Railway auto-deploys on push!
```

### If deploying directly:
1. Make changes locally
2. In Railway dashboard, click "Deploy" → "Redeploy"

## Troubleshooting

### App won't start:
- Check logs in Railway dashboard
- Verify all required environment variables are set
- Make sure Python version is compatible (3.9+)

### Calls fail:
- Verify Twilio webhook URLs are correct
- Check Railway logs for errors
- Ensure PUBLIC_BASE is being detected correctly (check logs for "[DEBUG] Running on Railway:")

### No emails sending:
- Verify RESEND_API_KEY or email service credentials
- Check FROM_EMAIL is verified in your email service
- Check Railway logs for email errors

## Cost Estimate

Railway Pricing:
- **Starter Plan:** $5/month
- **Usage-based:** ~$0.000231 per hour of uptime
- **Estimated:** $5-10/month for 24/7 operation

This is significantly cheaper than missing even one business call!

## Rollback

If something goes wrong:

1. In Railway dashboard, go to "Deployments"
2. Find a previous working deployment
3. Click "Redeploy"

Or restore from your backup:
```bash
cd /Users/anthony/aiagent
cp backups/20251026_120938_working_version/* .
```

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Bolt AI Issues: Check your Railway logs first

## Next Steps After Deployment

1. ✅ Test thoroughly with multiple calls
2. ✅ Monitor logs for first 24 hours
3. ✅ Set up custom domain (optional, ~$10/year)
4. ✅ Configure Railway alerts for downtime
5. ✅ Decommission Mac setup (stop launchd services)
