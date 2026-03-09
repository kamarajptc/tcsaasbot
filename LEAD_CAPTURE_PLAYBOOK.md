# Lead Capture System - Complete Playbook

## Overview

This playbook guides you through creating, testing, and validating the complete lead capture system in TangentCloud. By following these steps, you'll have a fully functional lead generation pipeline with forms, submissions, storage, and analytics.

---

## Prerequisites

- ✅ Backend running on port 9100
- ✅ PostgreSQL database connected
- ✅ Dashboard accessible on port 9101
- ✅ All services started (see `status_all.sh`)

**Verify services are running:**
```bash
ps aux | grep -E "uvicorn|next|expo" | grep -v grep
```

---

## Automated Playbook Execution

The fastest way to run all tests is using the automated Python script:

```bash
cd /Users/kamarajp/TCSAASBOT
source backend/venv/bin/activate
python3 lead_capture_playbook.py
```

**This will:**
1. ✓ Create a test bot
2. ✓ Set up a 7-field lead form
3. ✓ Validate form retrieval
4. ✓ Create a test conversation
5. ✓ Submit 3 test leads
6. ✓ Verify database records
7. ✓ Generate analytics report
8. ✓ Provide summary and next steps

**Expected output:**
```
======================================================================
                    STEP 1: CREATE TEST BOT
======================================================================

Step 1: Creating test bot
✓ Bot created: ID=123, Name=Lead Capture Test Bot
```

---

## Manual Step-by-Step Guide

If you prefer manual testing, follow these steps:

### Step 1: Create a Bot

```bash
# Get your auth token first
TOKEN=$(python3 -c "
import sys; sys.path.insert(0, 'backend')
from app.core.security import create_access_token
token = create_access_token({'sub': 'test-lead', 'tenant_id': 'test-lead'})
print(token)
")

# Create bot via curl
curl -X POST http://localhost:9100/api/v1/dashboard/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "Lead Capture Demo",
    "description": "Test bot for lead capture",
    "prompt_template": "You are helpful.",
    "welcome_message": "Welcome! How can I help?",
    "primary_color": "#3b82f6"
  }' | jq '.'
```

**Response:**
```json
{
  "id": 123,
  "name": "Lead Capture Demo",
  "tenant_id": "test-lead",
  "is_active": true,
  ...
}
```

**Save the `id` for next steps** → BOT_ID=123

---

### Step 2: Create a Lead Form

```bash
curl -X POST http://localhost:9100/api/v1/leads/forms \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "bot_id": 123,
    "title": "Contact Us - Schedule Demo",
    "fields": [
      {
        "name": "full_name",
        "label": "Full Name",
        "type": "text",
        "required": true
      },
      {
        "name": "email",
        "label": "Email Address",
        "type": "email",
        "required": true
      },
      {
        "name": "phone",
        "label": "Phone",
        "type": "text",
        "required": true
      },
      {
        "name": "company",
        "label": "Company",
        "type": "text",
        "required": false
      },
      {
        "name": "budget",
        "label": "Budget",
        "type": "dropdown",
        "required": true,
        "options": ["<$10k", "$10k-50k", "$50k+"]
      }
    ]
  }' | jq '.'
```

**Response:**
```json
{
  "id": 1,
  "bot_id": 123,
  "title": "Contact Us - Schedule Demo",
  "fields": [...],
  "is_active": true
}
```

**Save the form `id`** → FORM_ID=1

---

### Step 3: Retrieve Form (Verify Storage)

```bash
# Public endpoint (no auth needed for active forms)
curl -X GET "http://localhost:9100/api/v1/leads/forms/123" | jq '.'

# Admin endpoint (with auth)
curl -X GET "http://localhost:9100/api/v1/leads/forms/123/admin" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

**Verify:**
- ✓ Form ID matches what you created
- ✓ All 5 fields are present
- ✓ Field types are correct

---

### Step 4: Create a Test Conversation

```bash
curl -X POST http://localhost:9100/api/v1/chat/conversations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "bot_id": 123,
    "messages": [
      {
        "role": "user",
        "content": "I want to schedule a demo"
      },
      {
        "role": "bot",
        "content": "Great! Let me collect your information."
      }
    ]
  }' | jq '.'
```

**Response:**
```json
{
  "id": 456,
  "bot_id": 123,
  "tenant_id": "test-lead",
  ...
}
```

**Save the conversation `id`** → CONV_ID=456

---

### Step 5: Submit a Lead

This is the critical flow - when a user fills out the form in the chat.

```bash
curl -X POST http://localhost:9100/api/v1/leads/submit \
  -H "Content-Type: application/json" \
  -d '{
    "bot_id": 123,
    "conversation_id": 456,
    "data": {
      "full_name": "John Smith",
      "email": "john@acmecorp.com",
      "phone": "+1-555-0123",
      "company": "Acme Corp",
      "budget": "$50k+"
    },
    "country": "US",
    "source": "Widget"
  }' | jq '.'
```

**Response:**
```json
{
  "id": 1,
  "bot_id": 123,
  "conversation_id": 456,
  "data": {
    "full_name": "John Smith",
    "email": "john@acmecorp.com",
    ...
  },
  "country": "US",
  "source": "Widget",
  "created_at": "2026-03-06T16:45:00"
}
```

**Save the lead `id`** → LEAD_ID=1

---

### Step 6: Retrieve All Leads

```bash
curl -X GET http://localhost:9100/api/v1/leads/leads \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

**Verify:**
- ✓ Your lead appears in the list
- ✓ All data fields are present
- ✓ Timestamp is recent

---

### Step 7: Direct Database Verification

```bash
# Connect to PostgreSQL
psql -U postgres -d tangentcloud -c "
  SELECT id, bot_id, data, country, created_at 
  FROM leads 
  WHERE tenant_id = 'test-lead' 
  ORDER BY created_at DESC 
  LIMIT 5;
"
```

**Expected output:**
```
 id | bot_id |                         data                         | country |      created_at
----+--------+---------------------------------------------------------+---------+---------------------
  1 |    123 | {"full_name": "John Smith", "email": "john@..."}       | US      | 2026-03-06 16:45:00
```

---

## Validation Checklist

Use this checklist to verify everything is working:

### API Endpoints
- [ ] `POST /api/v1/leads/forms` - Create lead form
- [ ] `GET /api/v1/leads/forms/{bot_id}` - Public form retrieval
- [ ] `GET /api/v1/leads/forms/{bot_id}/admin` - Admin form retrieval
- [ ] `POST /api/v1/leads/submit` - Submit lead data
- [ ] `GET /api/v1/leads/leads` - List all leads

### Database Tables
- [ ] `lead_forms` table has records
- [ ] `leads` table has submitted records
- [ ] Data is properly JSON-encoded
- [ ] Timestamps are accurate
- [ ] Tenant isolation is working (different tenants see own data)

### Features
- [ ] Required field validation works
- [ ] Field types are preserved (email, dropdown, etc.)
- [ ] Custom field metadata stored
- [ ] Multiple form submissions work
- [ ] Lead data integrity maintained

### Dashboard
- [ ] Navigate to http://localhost:9101
- [ ] Go to Analytics → Leads
- [ ] See "Captured Leads" count increase
- [ ] Click on a lead to view details
- [ ] Verify all submitted data appears

---

## Test Scenarios

### Scenario 1: Happy Path (Complete Form)
```json
{
  "full_name": "John Smith",
  "email": "john@example.com",
  "phone": "+1-555-0123",
  "company": "Acme",
  "budget": "$50k+"
}
```
**Expected**: ✓ Lead created, all fields populated

### Scenario 2: Minimal Form (Only Required Fields)
```json
{
  "full_name": "Jane Doe",
  "email": "jane@example.com",
  "phone": "+1-555-0124",
  "budget": "$10k-50k"
}
```
**Expected**: ✓ Lead created, optional fields empty

### Scenario 3: Missing Required Field
```json
{
  "full_name": "Bob Johnson",
  "email": "bob@example.com"
  // phone is missing (required)
}
```
**Expected**: ✗ Form validation should reject (implement if needed)

### Scenario 4: Invalid Email
```json
{
  "full_name": "Test User",
  "email": "not-an-email",
  "phone": "+1-555-0125",
  "budget": "$100k+"
}
```
**Expected**: ✗ Email validation should catch (implement if needed)

---

## Expected Results

After running the complete playbook, you should have:

### Database State
```sql
-- Bots
SELECT COUNT(*) FROM bots WHERE tenant_id = 'test-lead';
-- Result: 1

-- Lead Forms
SELECT COUNT(*) FROM lead_forms WHERE tenant_id = 'test-lead';
-- Result: 1

-- Submitted Leads
SELECT COUNT(*) FROM leads WHERE tenant_id = 'test-lead';
-- Result: 3+ (initial + Alice + Bob)

-- Conversations
SELECT COUNT(*) FROM conversations WHERE tenant_id = 'test-lead';
-- Result: 1+
```

### API Response Examples

**Get Leads Response:**
```json
[
  {
    "id": 1,
    "bot_id": 123,
    "conversation_id": 456,
    "data": {
      "full_name": "John Smith",
      "email": "john@acmecorp.com",
      "phone": "+1-555-0123",
      "company": "Acme Corp",
      "budget": "$50k+"
    },
    "country": "US",
    "source": "Widget",
    "created_at": "2026-03-06T16:45:00"
  },
  {
    "id": 2,
    "bot_id": 123,
    "conversation_id": 456,
    "data": {
      "full_name": "Alice Johnson",
      "email": "alice@techcompany.com",
      ...
    },
    "country": "US",
    "source": "API_Test",
    "created_at": "2026-03-06T16:46:00"
  }
]
```

### Dashboard Metrics
- Captured Leads: 3+
- Lead conversion rate: Displayed on Intelligence Report
- Lead sources: Widget, API_Test breakdown
- Lead geography: US, UK distribution

---

## Troubleshooting

### Issue: 404 on `/leads/forms`
```
Error: {"detail":"Not found"}
```
**Solution**: Form doesn't exist or bot_id is incorrect
```bash
# Verify bot exists
curl http://localhost:9100/api/v1/dashboard/ \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {id, name}'
```

### Issue: 401 on Lead Submit
```
Error: {"detail":"Authentication required"}
```
**Solution**: Lead submit endpoint doesn't require auth (public)
- Remove `Authorization` header for `/leads/submit`
- But DO include it for `/leads/leads` (admin endpoint)

### Issue: Leads Not Appearing in Dashboard
```
Captured Leads: 0
```
**Solutions**:
1. Refresh the dashboard page (F5)
2. Check analytics hasn't filtered by date range
3. Verify tenant_id matches in database
4. Check leads are committed to PostgreSQL:
   ```sql
   SELECT COUNT(*) FROM leads;
   ```

### Issue: Database Connection Error
```
Error: can't connect to PostgreSQL
```
**Solution**: Start PostgreSQL service
```bash
brew services start postgresql
# or
postgres -D /usr/local/var/postgres
```

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Email notifications configured (SMTP settings)
- [ ] Slack webhooks configured (if using)
- [ ] Required field validation implemented
- [ ] Email/phone validation added
- [ ] Rate limiting on lead submit
- [ ] GDPR compliance (data retention policy)
- [ ] Lead scoring system (if needed)
- [ ] CRM integration tested
- [ ] Backup strategy for leads database
- [ ] Monitoring/alerting for lead capture failures

---

## Performance Benchmarks

After running the playbook, you should see:

| Operation | Expected Time |
|-----------|--------------|
| Create Bot | <500ms |
| Create Form | <200ms |
| Submit Lead | <300ms |
| Retrieve Leads List | <500ms |
| Database Write | <50ms |
| Database Read | <20ms |

---

## Advanced: Custom Lead Processing

To add custom logic to lead submissions, modify:
```python
# File: backend/app/api/v1/leads.py
# Function: submit_lead (line 126)

@router.post("/submit", response_model=LeadResponse)
async def submit_lead(submission: LeadSubmit, db: Session = Depends(get_db)):
    # 1. Validate lead data
    # 2. Save to database
    # 3. Send email notification
    # 4. Send Slack webhook
    # 5. Call CRM integration
    # 6. Call lead scoring service
    # 7. Return response
```

Examples:
- Add lead scoring based on budget/company size
- Send to Zapier webhook
- Sync with HubSpot/Salesforce
- Trigger email sequence
- Create CRM contact

---

## Support

For issues or questions:
1. Check logs: `tail -f backend.out`
2. Run playbook with verbose output
3. Verify database state with SQL queries
4. Check API responses with `curl -v`

---

**That's it! Your lead capture system is now validated and production-ready.** 🎉
