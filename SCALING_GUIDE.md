# Bolt AI Group - Scaling Guide

## Current Free Tier Setup

You're currently running on mostly free plans. Here's what you're using:

### Current Stack
- **Supabase**: Free tier (500MB database, 50,000 monthly active users)
- **Twilio**: Pay-as-you-go (no monthly fee, but per-minute charges)
- **OpenAI**: Pay-as-you-go (gpt-4o-mini is very cost-effective)
- **ElevenLabs**: Free tier (10,000 characters/month)
- **Ngrok**: Free tier (1 tunnel, random URLs)
- **Google Calendar API**: Free (quotas apply)

---

## When to Upgrade (Based on Client Count)

### 1-5 Clients (Current Phase)
**Keep everything as-is**. Your costs will be minimal:
- Twilio: ~$1-2 per phone number/month + $0.013/min for calls
- OpenAI: ~$0.15 per 1M input tokens (extremely cheap)
- ElevenLabs: Free tier is fine for testing

**Action Required:**
- Upgrade ngrok to paid ($8/month) for **permanent domain**
  - Why: You need a fixed PUBLIC_BASE_URL for Twilio webhooks
  - Current issue: ngrok free tier gives random URLs that change on restart
  - Fixed domain prevents having to reconfigure Twilio webhooks constantly

---

### 6-20 Clients (Growing Phase)
**Estimated Monthly Revenue**: $600-2,000 (at $99/client)

**Required Upgrades:**

1. **Ngrok → Permanent Hosting** ($5-20/month)
   - Options: Railway.app, Render.com, DigitalOcean App Platform
   - Why: More reliable than ngrok, better for production
   - Cost: $5-10/month for basic tier

2. **ElevenLabs Paid Plan** ($5-99/month)
   - Free tier: 10,000 chars/month (~6-8 calls)
   - Starter plan: $5/month for 30,000 chars (~20 calls)
   - Creator plan: $22/month for 100,000 chars (~65 calls)
   - Why: Better voice quality, more characters
   - When: Once you hit 5+ active clients making regular calls

3. **Twilio Phone Numbers** ($1/number/month)
   - Each client needs their own phone number
   - Cost: $1-2/month per number depending on type (local/toll-free)
   - You're already paying for one: +18555287028

**Performance Improvements:**
- Faster TTS with ElevenLabs Turbo v2.5 (already using this)
- More reliable uptime with proper hosting
- Fixed webhook URLs (no more ngrok restarts)

**Estimated Monthly Costs**: $50-150 (hosting + ElevenLabs + phone numbers)
**Profit Margin**: 85-92%

---

### 21-50 Clients (Scaling Phase)
**Estimated Monthly Revenue**: $2,100-5,000

**Required Upgrades:**

1. **Supabase Pro** ($25/month)
   - Free tier: 500MB database, 2GB bandwidth
   - Pro tier: 8GB database, 50GB bandwidth, daily backups
   - Why: More database space for call logs, better performance
   - When: Database approaches 400MB or you need daily backups

2. **OpenAI Usage Tier Upgrade** (automatic)
   - You'll automatically move to higher rate limits as usage grows
   - Cost stays the same per token, just higher limits
   - gpt-4o-mini is still extremely cheap (~$0.15 per 1M tokens)

3. **Better Hosting** ($20-50/month)
   - Railway Pro: $20/month
   - Render Standard: $25/month
   - DigitalOcean: $12-24/month
   - Why: Better uptime SLA, more resources, autoscaling

4. **Twilio Elastic SIP Trunking** (optional)
   - If doing high call volumes, can reduce per-minute costs
   - Requires more setup, only worth it at scale

**Performance Improvements:**
- Faster database queries with Supabase Pro
- Better uptime with production hosting
- Connection pooling for database (add pgBouncer)

**Estimated Monthly Costs**: $200-400
**Profit Margin**: 88-92%

---

### 50+ Clients (Enterprise Phase)
**Estimated Monthly Revenue**: $5,000+

**Required Upgrades:**

1. **Infrastructure**
   - Dedicated server or managed service
   - Redis for session management (currently in-memory)
   - Load balancer for multiple app instances
   - Cost: $100-300/month

2. **Monitoring & Analytics**
   - Datadog or New Relic: $15-100/month
   - Error tracking (Sentry): $26/month
   - Uptime monitoring (UptimeRobot Pro): $7/month

3. **Consider Multi-Region Deployment**
   - Lower latency for clients across US
   - Higher availability
   - Cost: +$50-200/month

**Estimated Monthly Costs**: $500-1,000
**Profit Margin**: 80-90%

---

## Technology-Specific Upgrade Benefits

### Supabase Free → Pro ($25/month)
- **8GB database** vs 500MB (16x increase)
- **Daily backups** (critical for client data)
- **Better performance** (connection pooling, optimized queries)
- **99.9% uptime SLA**
- **When**: Database >400MB or 20+ active clients

### ElevenLabs Free → Starter ($5/month)
- **30,000 chars/month** vs 10,000 (3x increase)
- ~20 full calls per month vs ~6-8
- **When**: 5+ clients or heavy call volume
- **Alternative**: Switch to Twilio TTS (cheaper at scale, lower quality)

### OpenAI API (already pay-as-you-go)
- No "upgrade" needed, just scales with usage
- gpt-4o-mini is extremely cost-effective
- At 1,000 calls/month: ~$5-10 in API costs
- **Consider**: gpt-4o (not mini) for premium clients willing to pay more

### Ngrok Free → Paid ($8/month)
- **Fixed domain** (no more random URLs)
- **More tunnels** (useful for testing)
- **Reserved domain** (professional look)
- **When**: As soon as you have 1 paying client

### Twilio (already pay-as-you-go)
- **Phone numbers**: $1-2/month each (required per client)
- **Call costs**: $0.013/min inbound, $0.014/min outbound
- **SMS**: $0.0079/message (for follow-ups)
- No upgrade needed, just scales linearly

---

## Recommended Upgrade Timeline

### Week 1 (Now)
- [ ] Keep all free tiers
- [ ] Test sales flow with current setup
- [x] Platform is running and configured

### First Paying Client
- [ ] Upgrade ngrok to paid ($8/month) for fixed domain
- [ ] Purchase dedicated Twilio number for client ($1-2/month)
- [ ] Update Twilio webhook URLs to fixed ngrok domain

### 3-5 Clients
- [ ] Upgrade ElevenLabs to Starter ($5/month)
- [ ] Consider Railway/Render hosting ($10-20/month)
- [ ] Move from ngrok to permanent hosting

### 10 Clients
- [ ] Monitor Supabase database size
- [ ] Consider Supabase Pro if approaching 400MB
- [ ] Add monitoring (UptimeRobot free tier is fine initially)

### 20+ Clients
- [ ] Upgrade to Supabase Pro ($25/month)
- [ ] Better hosting tier ($25-50/month)
- [ ] Add Redis for session management
- [ ] Implement connection pooling

---

## Cost Breakdown Examples

### 5 Clients ($995/month revenue)
- Ngrok Pro: $8
- ElevenLabs Starter: $5
- Twilio numbers (5): $10
- Twilio call costs: ~$20-40
- OpenAI API: ~$5
- **Total**: ~$48-68/month
- **Profit**: ~$927-947/month (93-95% margin)

### 20 Clients ($3,980/month revenue)
- Railway hosting: $20
- Supabase Pro: $25
- ElevenLabs Creator: $22
- Twilio numbers (20): $40
- Twilio call costs: ~$100-200
- OpenAI API: ~$15-25
- **Total**: ~$222-332/month
- **Profit**: ~$3,648-3,758/month (92-94% margin)

### 50 Clients ($9,950/month revenue)
- Railway Pro: $50
- Supabase Pro: $25
- ElevenLabs Pro: $99
- Twilio numbers (50): $100
- Twilio call costs: ~$300-500
- OpenAI API: ~$40-60
- Monitoring: $30
- **Total**: ~$644-864/month
- **Profit**: ~$9,086-9,306/month (91-94% margin)

---

## Performance Improvements by Upgrade

### Ngrok → Permanent Hosting
- **Uptime**: 95% → 99.9%
- **Response time**: Variable → Consistent
- **Reliability**: Restarts break webhooks → Always available

### ElevenLabs Free → Paid
- **Voice quality**: Good → Excellent
- **Latency**: ~1-2s → ~0.5-1s
- **Characters**: 10k/month → 30k-100k/month

### Supabase Free → Pro
- **Query speed**: Good → 2-3x faster
- **Concurrent connections**: 60 → 200
- **Backups**: None → Daily automated
- **Support**: Community → Email support

### Add Redis
- **Session lookup**: Database query → In-memory (10-100x faster)
- **Scalability**: Single instance → Multiple instances
- **Reliability**: Lost on restart → Persistent

---

## When NOT to Upgrade

- **Don't upgrade Supabase** until database >400MB or you need backups
- **Don't upgrade ElevenLabs** if using <10,000 chars/month (check dashboard)
- **Don't add Redis** until you have multiple app instances
- **Don't upgrade OpenAI** - gpt-4o-mini is already perfect for this use case

---

## Alternative Cost-Saving Options

### Voice (Instead of ElevenLabs)
- **Twilio TTS (Polly)**: Already included, free with calls
  - Pros: No extra cost, scales infinitely
  - Cons: Lower quality, more robotic
  - **When to use**: Budget clients who don't care about voice quality

### Database (Instead of Supabase Pro)
- **PostgreSQL on Railway**: Included with hosting
  - Pros: No separate database cost
  - Cons: Less managed, you handle backups
  - **When to use**: If already on Railway and database <1GB

### Hosting (Instead of Railway/Render)
- **Fly.io**: $0-5/month for small apps
- **DigitalOcean Droplet**: $6/month for VPS
  - Pros: Cheaper than managed services
  - Cons: More technical setup required
  - **When to use**: If you're comfortable with server management

---

## Bottom Line

**You're in great shape.** The current free/pay-as-you-go setup can easily handle 1-5 clients. Your biggest upgrade will be **ngrok → permanent hosting** once you get your first paying client.

**Key point**: At $199/client, even with ALL upgrades, you maintain 90-95% profit margins. The SaaS model is highly profitable.

**Next milestone**: Get 1 client, then upgrade ngrok. Everything else can wait until you hit 5-10 clients.
