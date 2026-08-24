# Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
# Author: Rohit Kumar Chandan
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0

"""
SaaS Record Formatter
=====================
Converts raw SaaS API records into natural language text for semantic search.
Each record becomes a human-readable description optimized for embedding.

Supported Providers:
- HubSpot (CRM): deals, contacts, companies, tickets
- Salesforce (CRM): opportunities, accounts, contacts, leads
- Stripe (Finance): customers, subscriptions, invoices, charges
- Pipedrive (CRM): deals, persons, organizations
- Zendesk (Support): tickets, users
- QuickBooks (Finance): invoices, customers, payments
- Intercom (Support): contacts, conversations, companies
- Notion (Productivity): databases, pages
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def format_date(date_value: Any) -> str:
    """Format date value to human-readable string."""
    if not date_value:
        return "Unknown"
    
    try:
        if isinstance(date_value, str):
            # Handle ISO format
            if 'T' in date_value:
                dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            else:
                dt = datetime.strptime(date_value[:10], '%Y-%m-%d')
            return dt.strftime('%B %d, %Y')
        elif isinstance(date_value, (int, float)):
            # Unix timestamp (Stripe uses seconds)
            dt = datetime.fromtimestamp(date_value)
            return dt.strftime('%B %d, %Y')
        elif isinstance(date_value, datetime):
            return date_value.strftime('%B %d, %Y')
    except Exception as e:
        logger.warning(f"Date format error for value '{date_value}' (type={type(date_value).__name__}): {e}")
    
    return str(date_value)


def format_currency(amount: Any, currency: str = "USD") -> str:
    """Format amount as currency string."""
    if amount is None:
        return "Unknown"
    
    try:
        amount = float(amount)
        return f"${amount:,.2f} {currency.upper()}"
    except (ValueError, TypeError):
        return str(amount)


def format_stage(stage: str, provider: str = "hubspot") -> str:
    """Format deal/opportunity stage to human-readable."""
    if not stage:
        return "Unknown"
    
    stage_mappings = {
        # HubSpot deal stages
        "appointmentscheduled": "Appointment Scheduled",
        "qualifiedtobuy": "Qualified to Buy",
        "presentationscheduled": "Presentation Scheduled",
        "decisionmakerboughtin": "Decision Maker Bought In",
        "contractsent": "Contract Sent",
        "closedwon": "Closed Won",
        "closedlost": "Closed Lost",
        
        # Salesforce stages
        "prospecting": "Prospecting",
        "qualification": "Qualification",
        "needs analysis": "Needs Analysis",
        "value proposition": "Value Proposition",
        "id. decision makers": "Identifying Decision Makers",
        "perception analysis": "Perception Analysis",
        "proposal/price quote": "Proposal/Price Quote",
        "negotiation/review": "Negotiation/Review",
        "closed won": "Closed Won",
        "closed lost": "Closed Lost",
    }
    
    return stage_mappings.get(stage.lower(), stage.replace("_", " ").title())


# =============================================================================
# HUBSPOT FORMATTERS
# =============================================================================

def format_hubspot_deal(record: Dict[str, Any]) -> str:
    """Format HubSpot deal record as natural language."""
    props = record.get('properties', record)
    
    name = props.get('dealname', 'Unnamed Deal')
    amount = props.get('amount')
    stage = format_stage(props.get('dealstage', ''), 'hubspot')
    close_date = format_date(props.get('closedate'))
    pipeline = props.get('pipeline', 'Default Pipeline')
    owner = props.get('hubspot_owner_id', 'Unassigned')
    create_date = format_date(props.get('createdate'))
    
    amount_str = f"${float(amount):,.0f}" if amount is not None else "Amount not specified"
    
    # Include object_type keywords for semantic search: deal, deals, opportunity
    return f"""[HubSpot Deal] {name}
Type: Deal / Sales Opportunity
Amount: {amount_str}
Stage: {stage}
Close Date: {close_date}
Pipeline: {pipeline}
Created: {create_date}
Source: HubSpot CRM
Keywords: deal, deals, opportunity, sales, revenue"""


def format_hubspot_contact(record: Dict[str, Any]) -> str:
    """Format HubSpot contact record as natural language."""
    props = record.get('properties', record)
    
    first = props.get('firstname', '')
    last = props.get('lastname', '')
    name = f"{first} {last}".strip() or "Unknown Contact"
    email = props.get('email', 'No email')
    company = props.get('company', 'Unknown Company')
    title = props.get('jobtitle', '')
    lifecycle = props.get('lifecyclestage', 'Unknown')
    lead_status = props.get('hs_lead_status', '')
    phone = props.get('phone', '')
    
    # Include object_type keywords for semantic search: contact, person, lead
    lines = [f"[HubSpot Contact] {name}"]
    lines.append("Type: Contact / Person / Lead")
    lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Phone: {phone}")
    lines.append(f"Company: {company}")
    if title:
        lines.append(f"Title: {title}")
    lines.append(f"Lifecycle Stage: {lifecycle.replace('_', ' ').title()}")
    if lead_status:
        lines.append(f"Lead Status: {lead_status}")
    lines.append("Source: HubSpot CRM")
    lines.append("Keywords: contact, contacts, person, people, lead, leads, customer")
    
    return "\n".join(lines)


def format_hubspot_company(record: Dict[str, Any]) -> str:
    """Format HubSpot company record as natural language."""
    props = record.get('properties', record)
    
    name = props.get('name', 'Unknown Company')
    domain = props.get('domain', 'No domain')
    industry = props.get('industry', 'Unknown Industry')
    employees = props.get('numberofemployees', '')
    revenue = props.get('annualrevenue')
    city = props.get('city', '')
    country = props.get('country', '')
    
    # Include object_type keywords for semantic search: company, organization, account
    lines = [f"[HubSpot Company] {name}"]
    lines.append("Type: Company / Organization / Account")
    lines.append(f"Domain: {domain}")
    lines.append(f"Industry: {industry}")
    if employees:
        lines.append(f"Employees: {employees}")
    if revenue:
        lines.append(f"Annual Revenue: ${float(revenue):,.0f}")
    location = ", ".join(filter(None, [city, country]))
    if location:
        lines.append(f"Location: {location}")
    lines.append("Source: HubSpot CRM")
    lines.append("Keywords: company, companies, organization, account, business")
    
    return "\n".join(lines)


def format_hubspot_ticket(record: Dict[str, Any]) -> str:
    """Format HubSpot ticket record as natural language."""
    props = record.get('properties', record)
    
    subject = props.get('subject', 'No Subject')
    content = props.get('content', '')
    priority = props.get('hs_ticket_priority', 'Normal')
    status = props.get('hs_pipeline_stage', 'Unknown')
    create_date = format_date(props.get('createdate'))
    
    # Include object_type keywords for semantic search: ticket, issue, support
    lines = [f"[HubSpot Ticket] {subject}"]
    lines.append("Type: Ticket / Support Issue / Case")
    lines.append(f"Priority: {priority}")
    lines.append(f"Status: {status}")
    lines.append(f"Created: {create_date}")
    if content:
        # Truncate long content
        content_preview = content[:200] + "..." if len(content) > 200 else content
        lines.append(f"Description: {content_preview}")
    lines.append("Source: HubSpot CRM")
    lines.append("Keywords: ticket, tickets, issue, support, case, help")
    
    return "\n".join(lines)


# =============================================================================
# SALESFORCE FORMATTERS
# =============================================================================

def format_salesforce_opportunity(record: Dict[str, Any]) -> str:
    """Format Salesforce opportunity record as natural language."""
    name = record.get('Name', 'Unnamed Opportunity')
    amount = record.get('Amount')
    stage = format_stage(record.get('StageName', ''), 'salesforce')
    close_date = format_date(record.get('CloseDate'))
    probability = record.get('Probability', 0)
    account_name = record.get('Account', {}).get('Name', 'Unknown Account') if isinstance(record.get('Account'), dict) else 'Unknown Account'
    opp_type = record.get('Type', '')
    
    amount_str = f"${float(amount):,.0f}" if amount is not None else "Amount not specified"
    
    # Include object_type keywords for semantic search: opportunity, deal
    lines = [f"[Salesforce Opportunity] {name}"]
    lines.append("Type: Opportunity / Deal / Sales")
    lines.append(f"Amount: {amount_str}")
    lines.append(f"Stage: {stage}")
    lines.append(f"Probability: {probability}%")
    lines.append(f"Close Date: {close_date}")
    lines.append(f"Account: {account_name}")
    if opp_type:
        lines.append(f"Opportunity Type: {opp_type}")
    lines.append("Source: Salesforce CRM")
    lines.append("Keywords: opportunity, opportunities, deal, deals, sales, revenue")
    
    return "\n".join(lines)


def format_salesforce_account(record: Dict[str, Any]) -> str:
    """Format Salesforce account record as natural language."""
    name = record.get('Name', 'Unknown Account')
    industry = record.get('Industry', 'Unknown Industry')
    account_type = record.get('Type', '')
    employees = record.get('NumberOfEmployees', '')
    revenue = record.get('AnnualRevenue')
    website = record.get('Website', '')
    phone = record.get('Phone', '')
    
    # Include object_type keywords for semantic search: account, company
    lines = [f"[Salesforce Account] {name}"]
    lines.append("Type: Account / Company / Organization")
    lines.append(f"Industry: {industry}")
    if account_type:
        lines.append(f"Account Type: {account_type}")
    if employees:
        lines.append(f"Employees: {employees}")
    if revenue:
        lines.append(f"Annual Revenue: ${float(revenue):,.0f}")
    if website:
        lines.append(f"Website: {website}")
    if phone:
        lines.append(f"Phone: {phone}")
    lines.append("Source: Salesforce CRM")
    lines.append("Keywords: account, accounts, company, companies, organization, business")
    
    return "\n".join(lines)


def format_salesforce_contact(record: Dict[str, Any]) -> str:
    """Format Salesforce contact record as natural language."""
    first = record.get('FirstName', '')
    last = record.get('LastName', '')
    name = f"{first} {last}".strip() or "Unknown Contact"
    email = record.get('Email', 'No email')
    title = record.get('Title', '')
    phone = record.get('Phone', '')
    account_name = record.get('Account', {}).get('Name', '') if isinstance(record.get('Account'), dict) else ''
    
    # Include object_type keywords for semantic search: contact, person
    lines = [f"[Salesforce Contact] {name}"]
    lines.append("Type: Contact / Person / Customer")
    lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Phone: {phone}")
    if title:
        lines.append(f"Title: {title}")
    if account_name:
        lines.append(f"Account: {account_name}")
    lines.append("Source: Salesforce CRM")
    lines.append("Keywords: contact, contacts, person, people, customer")
    
    return "\n".join(lines)


def format_salesforce_lead(record: Dict[str, Any]) -> str:
    """Format Salesforce lead record as natural language."""
    first = record.get('FirstName', '')
    last = record.get('LastName', '')
    name = f"{first} {last}".strip() or "Unknown Lead"
    email = record.get('Email', 'No email')
    company = record.get('Company', 'Unknown Company')
    status = record.get('Status', 'Unknown')
    source = record.get('LeadSource', '')
    title = record.get('Title', '')
    
    # Include object_type keywords for semantic search: lead, prospect
    lines = [f"[Salesforce Lead] {name}"]
    lines.append("Type: Lead / Prospect / Potential Customer")
    lines.append(f"Email: {email}")
    lines.append(f"Company: {company}")
    lines.append(f"Status: {status}")
    if title:
        lines.append(f"Title: {title}")
    if source:
        lines.append(f"Lead Source: {source}")
    lines.append("Source: Salesforce CRM")
    lines.append("Keywords: lead, leads, prospect, prospects, potential customer")
    
    return "\n".join(lines)


# =============================================================================
# STRIPE FORMATTERS
# =============================================================================

def format_stripe_customer(record: Dict[str, Any]) -> str:
    """Format Stripe customer record as natural language."""
    name = record.get('name') or record.get('email', 'Unknown Customer')
    email = record.get('email', 'No email')
    created = format_date(record.get('created'))
    balance = record.get('balance', 0) / 100  # Stripe uses cents
    currency = record.get('currency', 'usd').upper()
    phone = record.get('phone', '')
    description = record.get('description', '')
    
    lines = [f"[Stripe Customer] {name}"]
    lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Phone: {phone}")
    lines.append(f"Created: {created}")
    if balance != 0:
        lines.append(f"Balance: ${balance:,.2f} {currency}")
    if description:
        lines.append(f"Description: {description}")
    lines.append("Source: Stripe")
    lines.append("Type: Customer / Billing Account / Payer")
    lines.append("Keywords: customer, client, payer, billing, account, subscription holder")
    
    return "\n".join(lines)


def format_stripe_subscription(record: Dict[str, Any]) -> str:
    """Format Stripe subscription record as natural language."""
    customer_email = record.get('customer', {}).get('email', 'Unknown') if isinstance(record.get('customer'), dict) else record.get('customer', 'Unknown')
    status = record.get('status', 'Unknown').title()
    created = format_date(record.get('created'))
    current_period_end = format_date(record.get('current_period_end'))
    
    # Get plan details
    items = record.get('items', {}).get('data', [])
    plan_name = "Unknown Plan"
    amount = 0
    interval = "month"
    if items:
        plan = items[0].get('price', {}) or items[0].get('plan', {})
        plan_name = plan.get('nickname') or plan.get('product', 'Unknown Plan')
        amount = plan.get('unit_amount', 0) / 100
        interval = plan.get('interval', 'month')
    
    lines = [f"[Stripe Subscription] {customer_email}"]
    lines.append(f"Plan: {plan_name}")
    lines.append(f"Amount: ${amount:,.2f}/{interval}")
    lines.append(f"Status: {status}")
    lines.append(f"Created: {created}")
    lines.append(f"Current Period Ends: {current_period_end}")
    lines.append("Source: Stripe")
    lines.append("Type: Subscription / Recurring Payment / Plan")
    lines.append("Keywords: subscription, recurring, plan, membership, billing cycle, renewal")
    
    return "\n".join(lines)


def format_stripe_invoice(record: Dict[str, Any]) -> str:
    """Format Stripe invoice record as natural language."""
    customer_email = record.get('customer_email', 'Unknown')
    number = record.get('number', 'No number')
    status = record.get('status', 'Unknown').title()
    amount_due = record.get('amount_due', 0) / 100
    amount_paid = record.get('amount_paid', 0) / 100
    currency = record.get('currency', 'usd').upper()
    created = format_date(record.get('created'))
    due_date = format_date(record.get('due_date'))
    
    lines = [f"[Stripe Invoice] #{number}"]
    lines.append(f"Customer: {customer_email}")
    lines.append(f"Amount Due: ${amount_due:,.2f} {currency}")
    if amount_paid > 0:
        lines.append(f"Amount Paid: ${amount_paid:,.2f} {currency}")
    lines.append(f"Status: {status}")
    lines.append(f"Created: {created}")
    if due_date != "Unknown":
        lines.append(f"Due Date: {due_date}")
    lines.append("Source: Stripe")
    lines.append("Type: Invoice / Bill / Statement")
    lines.append("Keywords: invoice, bill, statement, payment due, billing, charge")
    
    return "\n".join(lines)


def format_stripe_charge(record: Dict[str, Any]) -> str:
    """Format Stripe charge record as natural language."""
    customer_email = record.get('billing_details', {}).get('email', 'Unknown')
    amount = record.get('amount', 0) / 100
    currency = record.get('currency', 'usd').upper()
    status = record.get('status', 'Unknown').title()
    created = format_date(record.get('created'))
    description = record.get('description', '')
    
    lines = [f"[Stripe Charge] ${amount:,.2f} {currency}"]
    lines.append(f"Customer: {customer_email}")
    lines.append(f"Status: {status}")
    lines.append(f"Date: {created}")
    if description:
        lines.append(f"Description: {description}")
    lines.append("Source: Stripe")
    lines.append("Type: Charge / Payment / Transaction")
    lines.append("Keywords: charge, payment, transaction, purchase, debit, payment processed")
    
    return "\n".join(lines)


# =============================================================================
# PIPEDRIVE FORMATTERS
# =============================================================================

def format_pipedrive_deal(record: Dict[str, Any]) -> str:
    """Format Pipedrive deal record as natural language."""
    title = record.get('title', 'Unnamed Deal')
    value = record.get('value', 0)
    currency = record.get('currency', 'USD')
    status = record.get('status', 'open').title()
    stage = record.get('stage', {})
    stage_name = stage.get('name', 'Unknown Stage') if isinstance(stage, dict) else 'Unknown Stage'
    person_name = record.get('person', {}).get('name', '') if isinstance(record.get('person'), dict) else ''
    org_name = record.get('organization', {}).get('name', '') if isinstance(record.get('organization'), dict) else ''
    
    lines = [f"[Pipedrive Deal] {title}"]
    lines.append(f"Value: ${value:,.0f} {currency}")
    lines.append(f"Stage: {stage_name}")
    lines.append(f"Status: {status}")
    if person_name:
        lines.append(f"Contact: {person_name}")
    if org_name:
        lines.append(f"Organization: {org_name}")
    lines.append("Source: Pipedrive CRM")
    lines.append("Type: Deal / Sales Opportunity / Pipeline")
    lines.append("Keywords: deal, opportunity, sales, pipeline, revenue, prospect")
    
    return "\n".join(lines)


def format_pipedrive_person(record: Dict[str, Any]) -> str:
    """Format Pipedrive person record as natural language."""
    name = record.get('name', 'Unknown Person')
    emails = record.get('email', [])
    email = emails[0].get('value', 'No email') if emails and isinstance(emails[0], dict) else 'No email'
    phones = record.get('phone', [])
    phone = phones[0].get('value', '') if phones and isinstance(phones[0], dict) else ''
    org_name = record.get('organization', {}).get('name', '') if isinstance(record.get('organization'), dict) else ''
    
    lines = [f"[Pipedrive Contact] {name}"]
    lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Phone: {phone}")
    if org_name:
        lines.append(f"Organization: {org_name}")
    lines.append("Source: Pipedrive CRM")
    lines.append("Type: Contact / Person / Lead")
    lines.append("Keywords: contact, person, lead, prospect, customer, individual")
    
    return "\n".join(lines)


def format_pipedrive_organization(record: Dict[str, Any]) -> str:
    """Format Pipedrive organization record as natural language."""
    name = record.get('name', 'Unknown Organization')
    address = record.get('address', '')
    
    lines = [f"[Pipedrive Organization] {name}"]
    if address:
        lines.append(f"Address: {address}")
    lines.append("Source: Pipedrive CRM")
    lines.append("Type: Organization / Company / Account")
    lines.append("Keywords: organization, company, account, business, firm, enterprise")
    
    return "\n".join(lines)


# =============================================================================
# ZENDESK FORMATTERS
# =============================================================================

def format_zendesk_ticket(record: Dict[str, Any]) -> str:
    """Format Zendesk ticket record as natural language."""
    subject = record.get('subject', 'No Subject')
    description = record.get('description', '')
    status = record.get('status', 'Unknown').title()
    priority = record.get('priority', 'Normal').title() if record.get('priority') else 'Normal'
    ticket_type = record.get('type', '').title()
    created = format_date(record.get('created_at'))
    
    lines = [f"[Zendesk Ticket] {subject}"]
    lines.append(f"Status: {status}")
    lines.append(f"Priority: {priority}")
    if ticket_type:
        lines.append(f"Type: {ticket_type}")
    lines.append(f"Created: {created}")
    if description:
        desc_preview = description[:200] + "..." if len(description) > 200 else description
        lines.append(f"Description: {desc_preview}")
    lines.append("Source: Zendesk")
    lines.append("Type: Ticket / Support Issue / Case / Request")
    lines.append("Keywords: ticket, support, issue, case, request, help desk, problem")
    
    return "\n".join(lines)


def format_zendesk_user(record: Dict[str, Any]) -> str:
    """Format Zendesk user record as natural language."""
    name = record.get('name', 'Unknown User')
    email = record.get('email', 'No email')
    role = record.get('role', 'Unknown').title()
    phone = record.get('phone', '')
    
    lines = [f"[Zendesk User] {name}"]
    lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Phone: {phone}")
    lines.append(f"Role: {role}")
    lines.append("Source: Zendesk")
    lines.append("Type: User / Agent / Customer")
    lines.append("Keywords: user, agent, customer, support agent, requester, end user")
    
    return "\n".join(lines)


# =============================================================================
# QUICKBOOKS FORMATTERS
# =============================================================================

def format_quickbooks_invoice(record: Dict[str, Any]) -> str:
    """Format QuickBooks invoice record as natural language."""
    doc_number = record.get('DocNumber', 'No number')
    customer_name = record.get('CustomerRef', {}).get('name', 'Unknown Customer') if isinstance(record.get('CustomerRef'), dict) else 'Unknown Customer'
    total = record.get('TotalAmt', 0)
    balance = record.get('Balance', 0)
    due_date = format_date(record.get('DueDate'))
    txn_date = format_date(record.get('TxnDate'))
    
    lines = [f"[QuickBooks Invoice] #{doc_number}"]
    lines.append(f"Customer: {customer_name}")
    lines.append(f"Total: ${total:,.2f}")
    if balance > 0:
        lines.append(f"Balance Due: ${balance:,.2f}")
    lines.append(f"Invoice Date: {txn_date}")
    lines.append(f"Due Date: {due_date}")
    lines.append("Source: QuickBooks")
    lines.append("Type: Invoice / Bill / Statement")
    lines.append("Keywords: invoice, bill, statement, payment due, accounting, receivable")
    
    return "\n".join(lines)


def format_quickbooks_customer(record: Dict[str, Any]) -> str:
    """Format QuickBooks customer record as natural language."""
    display_name = record.get('DisplayName', 'Unknown Customer')
    email = record.get('PrimaryEmailAddr', {}).get('Address', 'No email') if isinstance(record.get('PrimaryEmailAddr'), dict) else 'No email'
    phone = record.get('PrimaryPhone', {}).get('FreeFormNumber', '') if isinstance(record.get('PrimaryPhone'), dict) else ''
    balance = record.get('Balance', 0)
    
    lines = [f"[QuickBooks Customer] {display_name}"]
    lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Phone: {phone}")
    if balance > 0:
        lines.append(f"Balance: ${balance:,.2f}")
    lines.append("Source: QuickBooks")
    lines.append("Type: Customer / Client / Account")
    lines.append("Keywords: customer, client, account, buyer, payer, receivable")
    
    return "\n".join(lines)


# =============================================================================
# INTERCOM FORMATTERS
# =============================================================================

def format_intercom_contact(record: Dict[str, Any]) -> str:
    """Format Intercom contact record as natural language."""
    name = record.get('name', 'Unknown Contact')
    email = record.get('email', 'No email')
    role = record.get('role', 'user').title()
    phone = record.get('phone', '')
    
    lines = [f"[Intercom Contact] {name}"]
    lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Phone: {phone}")
    lines.append(f"Role: {role}")
    lines.append("Source: Intercom")
    lines.append("Type: Contact / User / Lead")
    lines.append("Keywords: contact, user, lead, visitor, prospect, customer")
    
    return "\n".join(lines)


def format_intercom_conversation(record: Dict[str, Any]) -> str:
    """Format Intercom conversation record as natural language."""
    title = record.get('title', 'Untitled Conversation')
    state = record.get('state', 'Unknown').title()
    priority = record.get('priority', 'Normal').title()
    created = format_date(record.get('created_at'))
    
    # Get last message preview
    source = record.get('source', {})
    body = source.get('body', '') if isinstance(source, dict) else ''
    
    lines = [f"[Intercom Conversation] {title}"]
    lines.append(f"State: {state}")
    lines.append(f"Priority: {priority}")
    lines.append(f"Created: {created}")
    if body:
        body_preview = body[:200] + "..." if len(body) > 200 else body
        lines.append(f"Preview: {body_preview}")
    lines.append("Source: Intercom")
    lines.append("Type: Conversation / Chat / Message Thread")
    lines.append("Keywords: conversation, chat, message, thread, discussion, support chat")
    
    return "\n".join(lines)


# =============================================================================
# NOTION FORMATTERS
# =============================================================================

def format_notion_page(record: Dict[str, Any]) -> str:
    """Format Notion page record as natural language."""
    props = record.get('properties', {})
    
    # Try to get title from various property types
    title = "Untitled Page"
    for key, value in props.items():
        if isinstance(value, dict):
            if value.get('type') == 'title':
                title_items = value.get('title', [])
                if title_items:
                    title = title_items[0].get('plain_text', 'Untitled')
                break
    
    created = format_date(record.get('created_time'))
    last_edited = format_date(record.get('last_edited_time'))
    
    lines = [f"[Notion Page] {title}"]
    lines.append(f"Created: {created}")
    lines.append(f"Last Edited: {last_edited}")
    lines.append("Source: Notion")
    lines.append("Type: Page / Document / Note")
    lines.append("Keywords: page, document, note, wiki, doc, content")
    
    return "\n".join(lines)


def format_notion_database(record: Dict[str, Any]) -> str:
    """Format Notion database record as natural language."""
    title_items = record.get('title', [])
    title = title_items[0].get('plain_text', 'Untitled Database') if title_items else 'Untitled Database'
    description = record.get('description', [])
    desc_text = description[0].get('plain_text', '') if description else ''
    
    lines = [f"[Notion Database] {title}"]
    if desc_text:
        lines.append(f"Description: {desc_text}")
    
    # List properties/columns
    properties = record.get('properties', {})
    if properties:
        prop_names = list(properties.keys())[:5]
        lines.append(f"Columns: {', '.join(prop_names)}")
    
    lines.append("Source: Notion")
    lines.append("Type: Database / Table / Collection")
    lines.append("Keywords: database, table, collection, spreadsheet, tracker, list")
    
    return "\n".join(lines)


# =============================================================================
# MAIN FORMATTER REGISTRY
# =============================================================================

FORMATTERS = {
    "hubspot": {
        "deal": format_hubspot_deal,
        "deals": format_hubspot_deal,
        "contact": format_hubspot_contact,
        "contacts": format_hubspot_contact,
        "company": format_hubspot_company,
        "companies": format_hubspot_company,
        "ticket": format_hubspot_ticket,
        "tickets": format_hubspot_ticket,
    },
    "salesforce": {
        "opportunity": format_salesforce_opportunity,
        "opportunities": format_salesforce_opportunity,
        "account": format_salesforce_account,
        "accounts": format_salesforce_account,
        "contact": format_salesforce_contact,
        "contacts": format_salesforce_contact,
        "lead": format_salesforce_lead,
        "leads": format_salesforce_lead,
    },
    "stripe": {
        "customer": format_stripe_customer,
        "customers": format_stripe_customer,
        "subscription": format_stripe_subscription,
        "subscriptions": format_stripe_subscription,
        "invoice": format_stripe_invoice,
        "invoices": format_stripe_invoice,
        "charge": format_stripe_charge,
        "charges": format_stripe_charge,
    },
    "pipedrive": {
        "deal": format_pipedrive_deal,
        "deals": format_pipedrive_deal,
        "person": format_pipedrive_person,
        "persons": format_pipedrive_person,
        "organization": format_pipedrive_organization,
        "organizations": format_pipedrive_organization,
    },
    "zendesk": {
        "ticket": format_zendesk_ticket,
        "tickets": format_zendesk_ticket,
        "user": format_zendesk_user,
        "users": format_zendesk_user,
    },
    "quickbooks": {
        "invoice": format_quickbooks_invoice,
        "invoices": format_quickbooks_invoice,
        "customer": format_quickbooks_customer,
        "customers": format_quickbooks_customer,
    },
    "intercom": {
        "contact": format_intercom_contact,
        "contacts": format_intercom_contact,
        "conversation": format_intercom_conversation,
        "conversations": format_intercom_conversation,
    },
    "notion": {
        "page": format_notion_page,
        "pages": format_notion_page,
        "database": format_notion_database,
        "databases": format_notion_database,
    },
    # File upload providers
    "file_upload": {
        "excel_row": None,  # Uses format_excel_row() directly
        "json_record": None,  # Uses format_json_record() directly
    },
}


# =============================================================================
# FILE UPLOAD FORMATTERS (Excel rows, JSON records)
# =============================================================================

def format_excel_row(record: Dict[str, Any]) -> str:
    """
    Format an Excel row record with file context header injection.
    
    Record structure:
    - file_context: {filename, sheet_name, headers, total_columns}
    - row_number: int
    - data: {column: value}
    - source_type: "excel_row"
    """
    ctx = record.get('file_context', {})
    filename = ctx.get('filename', 'Unknown File')
    sheet_name = ctx.get('sheet_name', 'Sheet1')
    headers = ctx.get('headers', [])
    row_number = record.get('row_number', 0)
    data = record.get('data', {})
    
    # Build header line with file context (injected into embedding)
    lines = [f"[File: {filename} | Sheet: {sheet_name}]"]
    lines.append("Type: Excel Row / Spreadsheet Record")
    
    # Add headers for context
    if headers:
        lines.append(f"Columns: {' | '.join(headers[:15])}")  # Max 15 columns in header
    
    # Add row data
    lines.append(f"Row {row_number}:")
    
    # Format each column value
    for col, value in data.items():
        if value == "" or value is None:
            continue
        
        # Format numbers nicely
        if isinstance(value, float):
            if value == int(value):
                formatted_value = str(int(value))
            else:
                formatted_value = f"{value:,.2f}"
        elif isinstance(value, int):
            formatted_value = f"{value:,}"
        else:
            formatted_value = str(value)[:200]  # Truncate long values
        
        lines.append(f"  {col}: {formatted_value}")
    
    # Add keywords for semantic search
    lines.append("Keywords: excel, spreadsheet, row, data, table, record")
    
    return "\n".join(lines)


def format_json_record(record: Dict[str, Any]) -> str:
    """
    Format a JSON object record with file context header injection.
    
    Record structure:
    - file_context: {filename, array_path, detected_type, total_objects}
    - object_index: int
    - data: dict (the actual JSON object)
    - source_type: "json_record"
    """
    ctx = record.get('file_context', {})
    filename = ctx.get('filename', 'Unknown File')
    detected_type = ctx.get('detected_type', 'record')
    array_path = ctx.get('array_path', 'root')
    obj_index = record.get('object_index', 0)
    data = record.get('data', {})
    
    # Build header line with file context (injected into embedding)
    lines = [f"[File: {filename} | Path: {array_path}]"]
    lines.append(f"Type: JSON {detected_type.title()} / Data Record")
    lines.append(f"Record #{obj_index + 1}:")
    
    # Format object fields
    for key, value in data.items():
        if value is None or value == "":
            continue
        
        # Handle nested objects/arrays
        if isinstance(value, dict):
            # Flatten one level
            nested_str = ", ".join(f"{k}: {v}" for k, v in list(value.items())[:5])
            formatted_value = f"{{{nested_str}}}"
        elif isinstance(value, list):
            if len(value) == 0:
                continue
            if isinstance(value[0], dict):
                formatted_value = f"[{len(value)} items]"
            else:
                formatted_value = ", ".join(str(v) for v in value[:5])
                if len(value) > 5:
                    formatted_value += f"... (+{len(value) - 5} more)"
        elif isinstance(value, float):
            if value == int(value):
                formatted_value = str(int(value))
            else:
                formatted_value = f"{value:,.2f}"
        elif isinstance(value, int):
            formatted_value = f"{value:,}"
        else:
            formatted_value = str(value)[:200]  # Truncate long values
        
        # Format key nicely
        display_key = key.replace('_', ' ').replace('-', ' ').title()
        lines.append(f"  {display_key}: {formatted_value}")
    
    # Add keywords based on detected type
    type_keywords = {
        "deal": "deal, deals, opportunity, sales, revenue, pipeline",
        "contact": "contact, person, lead, customer, email, phone",
        "company": "company, organization, account, business",
        "invoice": "invoice, billing, payment, amount, due",
        "ticket": "ticket, support, issue, request, helpdesk",
        "order": "order, purchase, shipping, fulfillment",
        "product": "product, item, sku, inventory, catalog",
        "record": "json, data, record, export, import",
    }
    keywords = type_keywords.get(detected_type, type_keywords["record"])
    lines.append(f"Keywords: {keywords}")
    
    return "\n".join(lines)


def format_record(
    record: Dict[str, Any],
    provider: str,
    object_type: str
) -> Optional[str]:
    """
    Format a SaaS record as natural language text for embedding.
    
    Args:
        record: Raw record data from SaaS API
        provider: Provider name (hubspot, salesforce, etc.)
        object_type: Object type (deal, contact, etc.)
    
    Returns:
        Formatted natural language string, or None if formatter not found
    """
    provider = provider.lower()
    object_type = object_type.lower()
    
    if provider not in FORMATTERS:
        logger.warning(f"No formatter for provider: {provider}")
        return None
    
    provider_formatters = FORMATTERS[provider]
    
    if object_type not in provider_formatters:
        logger.warning(f"No formatter for {provider}/{object_type}")
        return None
    
    try:
        formatter = provider_formatters[object_type]
        if formatter is None:
            logger.warning(f"Formatter for {provider}/{object_type} is None (use dedicated function)")
            return None
        return formatter(record)
    except Exception as e:
        logger.error(f"ALERT: Formatter error for {provider}/{object_type}: {e}", exc_info=True)
        # Return None so caller can skip this record rather than embedding a deceptive stub
        return None


def get_supported_objects(provider: str) -> list:
    """Get list of supported object types for a provider."""
    provider = provider.lower()
    if provider in FORMATTERS:
        # Return unique object types (remove singular/plural duplicates)
        objects = set()
        for obj_type in FORMATTERS[provider].keys():
            # Prefer plural form
            if obj_type.endswith('s') or obj_type + 's' not in FORMATTERS[provider]:
                objects.add(obj_type)
        return sorted(objects)
    return []


def get_all_providers() -> list:
    """Get list of all supported providers."""
    return sorted(FORMATTERS.keys())
