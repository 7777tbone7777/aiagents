# Demo Campaign Tracking Template

Copy this into a Google Sheet to track your campaign performance.

## Sheet 1: Campaign Overview

| Batch # | Date Sent | # Emails | Opens | Open Rate | Clicks | Click Rate | Demos Booked | Booking Rate | Demos Completed | Closed Deals |
|---------|-----------|----------|-------|-----------|--------|------------|--------------|--------------|-----------------|--------------|
| 1       | 2025-10-28 | 50      |       |           |        |            |              |              |                 |              |
| 2       | 2025-10-30 | 50      |       |           |        |            |              |              |                 |              |
| 3       | 2025-11-01 | 50      |       |           |        |            |              |              |                 |              |

**Formulas:**
- Open Rate: `=D2/C2` (format as percentage)
- Click Rate: `=F2/C2` (format as percentage)
- Booking Rate: `=H2/C2` (format as percentage)

---

## Sheet 2: Individual Contacts

Track which specific people booked demos:

| Email | Name | Company | Title | Batch # | Email Sent | Opened? | Clicked? | Demo Booked? | Demo Date | Demo Completed? | Next Steps | Status |
|-------|------|---------|-------|---------|------------|---------|----------|--------------|-----------|-----------------|------------|--------|
| john@example.com | John Doe | ABC Productions | Payroll Accountant | 1 | 2025-10-28 | Yes | Yes | Yes | 2025-11-02 3pm | Yes | Follow-up email sent | Qualified |

**Status Options:**
- Not Contacted
- Contacted
- Opened
- Clicked
- Demo Booked
- Demo Completed
- Qualified (interested in buying)
- Proposal Sent
- Closed Won
- Closed Lost

---

## Sheet 3: Best Subject Lines

Track which subject lines work best:

| Subject Line | # Sent | Opens | Open Rate | Clicks | Click Rate | Demos Booked |
|--------------|--------|-------|-----------|--------|------------|--------------|
| Quick question about your extras payroll process | 50 |  |  |  |  |  |
| Streamline your background payroll - 30 min demo? | 50 |  |  |  |  |  |
| Save 10+ hours/week on payroll (production accountants) | 50 |  |  |  |  |  |

This helps you identify which messaging resonates best.

---

## How to Pull Data

### From Mailchimp:
1. Go to Campaigns
2. Click on your campaign
3. Click "View Report"
4. See: Opens, Clicks, Click Rate
5. Click "View full report" → "Who opened" to see individual names

### From Calendly:
1. Go to your event type ("Product Demo")
2. Click "Analytics" or view "Scheduled Events"
3. Count total bookings
4. Export to CSV if needed

### Update Your Sheet:
- **Daily**: Check Mailchimp for opens/clicks
- **Weekly**: Update demo bookings from Calendly
- **After demos**: Mark completed and add next steps

---

## Key Metrics to Track

### Email Performance:
- **Target Open Rate**: 20-30% (cold email average)
- **Target Click Rate**: 2-5%
- **Target Booking Rate**: 1-3% (1-3 bookings per 100 emails)

### Demo Performance:
- **Show Rate**: % of booked demos that actually happen (target: 60-70%)
- **Qualified Rate**: % of demos that are good fit (target: 40-60%)
- **Close Rate**: % of demos that become customers (target: 10-30%)

### Example Math:
- 100 emails sent
- 25 opens (25% open rate) ✓
- 3 clicks (3% click rate) ✓
- 2 demos booked (2% booking rate) ✓
- 1 demo completed (50% show rate) - needs improvement
- 1 qualified lead (50% qualified rate) ✓
- 0 closed (0% close rate) - too early to tell

---

## Weekly Review Questions

Answer these every Friday:

1. **What subject line performed best this week?**
2. **What time of day got the most opens?** (check Mailchimp report)
3. **Which companies/titles are most interested?**
4. **What objections came up in demos?**
5. **What should I change in next week's emails?**

---

## Red Flags

Stop and adjust if:
- Open rate < 15% → Your subject lines aren't working or emails going to spam
- Click rate < 1% → Your email body isn't compelling
- Booking rate < 0.5% → Landing page or offer needs work
- Show rate < 50% → Too much friction, or wrong audience

---

## Sample Weekly Report Email (to yourself)

**Subject: Demo Campaign Week [X] Results**

Week ending: [Date]

**Emails Sent**: 150
**Opens**: 38 (25%)
**Clicks**: 5 (3.3%)
**Demos Booked**: 3 (2%)
**Demos Completed**: 2
**Qualified Leads**: 2
**Next Steps**: Follow up with 2 qualified leads by Wednesday

**Best Performing**:
- Subject: "Quick question about your extras payroll process" (30% open rate)
- Day: Tuesday at 10am
- Title: Production Accountants (5% booking rate vs 1% for other titles)

**Changes for Next Week**:
- Send more emails on Tuesday mornings
- Focus on production accountants (better fit)
- Try new subject line about "union compliance"

**Pipeline Status**:
- 5 demos booked for next week
- 2 proposals pending
- 0 closed deals (too early)

---

This tracking will help you optimize your campaign over time. Start simple with just Sheet 1, then add details as needed.
