# Demo Landing Page Setup Guide

## Total Cost: $0/month

This guide will help you set up a professional demo booking system with zero monthly costs.

---

## Part 1: Set Up Calendly (5 minutes)

### Step 1: Create Free Calendly Account
1. Go to https://calendly.com/signup
2. Sign up with your email (scarfaceforward@gmail.com)
3. Connect your Google Calendar

### Step 2: Create Demo Event Type
1. Click "New Event Type"
2. Select "One-on-One"
3. Configure:
   - **Event name**: "Product Demo"
   - **Duration**: 30 minutes
   - **Location**: Zoom (Calendly provides free Zoom integration)

### Step 3: Set Your Availability
1. Click "Availability" in sidebar
2. Set your working hours (when you're available for demos)
3. Example: Mon-Fri, 9am-5pm

### Step 4: Customize Questions
1. In your event settings, go to "Invitee Questions"
2. Add these custom fields:
   - Name (required) - already there
   - Email (required) - already there
   - Company Name (required)
   - Role/Title (required)
   - "What's your biggest payroll challenge?" (optional text area)

### Step 5: Get Your Calendly Link
1. Go to your "Product Demo" event
2. Click "Copy Link"
3. Your link will look like: `https://calendly.com/yourname/product-demo`
4. **Save this link** - you'll need it for Step 2

---

## Part 2: Host Landing Page on GitHub Pages (10 minutes)

### Step 1: Create GitHub Account (if you don't have one)
1. Go to https://github.com/signup
2. Sign up with your email

### Step 2: Create Repository
1. Click the "+" icon in top right → "New repository"
2. Repository name: `demo-landing`
3. Make it **Public**
4. Check "Add a README file"
5. Click "Create repository"

### Step 3: Upload Your Landing Page
1. In your new repository, click "Add file" → "Upload files"
2. Drag and drop the `index.html` file from `/Users/anthony/aiagent/demo-landing/`
3. If you have screenshots ready, upload them too
4. Click "Commit changes"

### Step 4: Customize the Landing Page
1. Click on `index.html` in your repository
2. Click the pencil icon to edit
3. Find and replace these placeholders:
   - `[COMPANY NAME]` → Your company name
   - `[YOUR VALUE PROPOSITION]` → Your pitch (e.g., "Save 10+ hours per week on background & extras payroll")
   - `YOUR_CALENDLY_LINK_HERE` → Your Calendly link from Part 1 Step 5
4. (Optional) Update the benefits list with your specific features
5. Click "Commit changes"

### Step 5: Enable GitHub Pages
1. Go to repository Settings (top menu)
2. Scroll down to "Pages" in left sidebar
3. Under "Source", select "Deploy from a branch"
4. Under "Branch", select "main" and "/root"
5. Click "Save"
6. Wait 2-3 minutes for deployment

### Step 6: Get Your Live URL
1. Go back to Settings → Pages
2. You'll see: "Your site is published at https://yourusername.github.io/demo-landing/"
3. **This is your landing page URL!** Save it.
4. Click it to test - your page should load

### Step 7: Add Screenshots (Do This Later)
1. Take 4 screenshots of your product
2. Save them as: `screenshot1.jpg`, `screenshot2.jpg`, etc.
3. Upload to your GitHub repository
4. Edit `index.html` and replace the placeholder divs with:
   ```html
   <img src="screenshot1.jpg" alt="Dashboard view">
   ```

---

## Part 3: Set Up Mailchimp for Email Campaign (15 minutes)

### Step 1: Create Free Mailchimp Account
1. Go to https://mailchimp.com/signup/
2. Sign up (Free plan: 500 contacts, 1,000 emails/month - enough for your first campaign)

### Step 2: Import Your Email List
1. Click "Audience" → "All contacts"
2. Click "Import contacts"
3. Upload your email list (CSV or Excel)
   - Required columns: Email, First Name, Last Name
   - Optional: Company, Title

### Step 3: Create Email Campaign
1. Click "Campaigns" → "Create Campaign"
2. Select "Email"
3. Name it "Demo Outreach - Wave 1"

### Step 4: Design Your Email
1. Select "Plain Text" template (better deliverability than HTML for cold emails)
2. Use the email template I'll create next

### Step 5: Add Tracking
1. In campaign settings, enable "Track opens" and "Track clicks"
2. This lets you see who's interested

---

## Part 4: Email Template

Here's the email template optimized for production accountants:

**Subject Lines (A/B test these):**
- Option 1: "Quick question about your extras payroll process"
- Option 2: "Streamline your background payroll - 30 min demo?"
- Option 3: "Save 10+ hours/week on payroll (production accountants)"

**Email Body:**
```
Hi [FIRST_NAME],

I noticed you work as a [TITLE] at [COMPANY]. I wanted to reach out because we've built something specifically for production accountants dealing with background and extras payroll.

Quick question: How much time do you spend each week processing payroll for extras?

We've helped production accountants reduce that time by 50% (some report saving 10+ hours per week) by automating:
• Union/non-union compliance tracking
• Bulk processing for hundreds of extras
• Real-time reporting for production teams
• Export-ready payroll reports

Would you be open to a quick 30-minute demo to see if this could help your workflow?

→ Click here to schedule: [YOUR GITHUB PAGES URL]

No pressure - just sharing in case it's helpful. Either way, happy to chat about what's working in your current process.

Best,
[YOUR NAME]
[YOUR TITLE]
[YOUR COMPANY]
[YOUR PHONE]
```

---

## Part 5: Launch Checklist

### Before Sending Emails:
- [ ] Calendly is set up with correct availability
- [ ] GitHub Pages landing page is live and loads correctly
- [ ] Calendly link in landing page works (test it yourself)
- [ ] Screenshots are added (or placeholders are acceptable for testing)
- [ ] Company name and value proposition are updated
- [ ] Mailchimp campaign is created
- [ ] Email list is imported to Mailchimp
- [ ] Email template is personalized

### Send Test First:
1. Send test email to yourself
2. Click the landing page link
3. Book a test demo appointment
4. Verify you receive confirmation email
5. Verify appointment shows in your Google Calendar

### Launch:
1. Send first batch of 50 emails (Mailchimp free tier allows this)
2. Wait 2-3 days to see response rate
3. Adjust email copy if needed
4. Send next batch

---

## Part 6: Track Results (Free Google Sheet)

Create a simple tracking sheet:

**Columns:**
- Date Sent
- Batch Number
- Emails Sent
- Emails Opened (from Mailchimp)
- Clicks (from Mailchimp)
- Demos Booked (from Calendly)
- Demos Completed
- Conversion to Customer

**How to Pull Data:**
- Mailchimp: Campaign Reports → See opens/clicks
- Calendly: Event Type → See scheduled events
- Manual: Track completed demos and conversions

---

## Costs Summary

| Service | Free Tier Limits | Cost |
|---------|-----------------|------|
| Calendly | Unlimited bookings, 1 event type | $0 |
| GitHub Pages | Unlimited hosting | $0 |
| Mailchimp | 500 contacts, 1,000 emails/month | $0 |
| Google Calendar | Unlimited events | $0 |
| **TOTAL** | | **$0/month** |

### When to Upgrade:
- **Mailchimp**: If you have >500 contacts, upgrade to Essentials ($13/month for 500 contacts)
- **Calendly**: If you need multiple event types or team scheduling, upgrade to Standard ($10/month)

---

## Timeline

- **Day 1** (1 hour): Set up Calendly + GitHub Pages + Customize landing page
- **Day 2** (1 hour): Set up Mailchimp + Import contacts + Create email template
- **Day 3**: Send test emails, make adjustments
- **Day 4**: Launch first batch (50 emails)
- **Week 2**: Send second batch based on results

---

## Need Help?

Common issues:
1. **Calendly not showing on page**: Make sure you replaced `YOUR_CALENDLY_LINK_HERE` with your actual link
2. **GitHub Pages not loading**: Wait 5 minutes after enabling, then try again
3. **Emails going to spam**: Use plain text template, personalize subject lines, send in small batches

Let me know if you hit any roadblocks!
