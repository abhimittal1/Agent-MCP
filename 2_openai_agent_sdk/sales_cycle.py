import os
from dotenv import load_dotenv, find_dotenv

# Load environment variables FIRST before importing any agent SDKs that might initialize clients
load_dotenv(find_dotenv(), override=True)

import smtplib
import imaplib
import email
import asyncio
import sys

# Ensure UTF-8 output to prevent UnicodeEncodeError in Windows terminals
sys.stdout.reconfigure(encoding='utf-8')

from email.message import EmailMessage
from email.header import decode_header

from agents import Agent, Runner, function_tool, ModelSettings

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_IMAP_SERVER = os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com")
TARGET_CUSTOMER_EMAIL = os.getenv("SMTP_SEND_TO")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")

# ==========================================
# 1. EMAIL HELPERS
# ==========================================

def send_email(subject, text_body, html_body, to_email=TARGET_CUSTOMER_EMAIL):
    """Sends an email using SMTP."""
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    print(f"\n[*] Sending email to {to_email}")
    print(f"[*] Subject: {subject}")
    with smtplib.SMTP(EMAIL_SMTP_SERVER, 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        server.send_message(msg)
    print("[*] Email sent successfully.")

def check_for_replies():
    """Checks the inbox using IMAP for any unread replies from the target customer."""
    try:
        mail = imaplib.IMAP4_SSL(EMAIL_IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        mail.select("inbox")

        # Search for UNREAD emails from the target customer
        status, messages = mail.search(None, 'UNSEEN', 'FROM', f'"{TARGET_CUSTOMER_EMAIL}"')
        # status, messages = mail.search(None, 'ALL')
        # print(status, messages)

        if status != "OK" or not messages[0]:
            mail.logout()
            return None

        email_ids = messages[0].split()
        for e_id in email_ids:
            # Fetch the email message by ID
            res, msg_data = mail.fetch(e_id, '(RFC822)')
            if res != "OK":
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Mark as read
                    mail.store(e_id, '+FLAGS', '\\Seen')

                    # Decode subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else 'utf-8')
                    
                    # Extract body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    mail.logout()
                    return {"subject": subject, "body": body}

        mail.logout()
        return None

    except Exception as e:
        print(f"[!] Error checking emails: {e}")
        return None

# ==========================================
# 2. DEFINING THE AGENTS
# ==========================================

company_intro = """
You are an elite sales agent working for Asteral AI, a forward-thinking tech company that builds custom apps tailored to specific customer needs.
Our offerings include:
- For business owners: Comprehensive business management apps and platforms to streamline operations and drive growth.
- For clothes shops: Smart clothes suggestion apps that help customers find the perfect outfits, leading to better experiences and faster selling.

You write highly attractive, persuasive, and personalized cold sales emails designed to maximize reply rates. Focus on the value and ROI we bring to their specific niche.
"""

# The 3 Writers
writer1 = Agent(
    name="Professional Writer", 
    instructions=company_intro + "Your email style is professional, serious, with gravitas and credibility. Highlight efficiency and growth. Ensure you include a Subject line.", 
    model=MODEL_NAME
)
writer2 = Agent(
    name="Humorous Writer", 
    instructions=company_intro + "Your email style is witty, engaging, and humorous. Make them smile and eager to reply. Ensure you include a Subject line.", 
    model=MODEL_NAME
)
writer3 = Agent(
    name="Executive Writer", 
    instructions=company_intro + "Your email style is concise, punchy, and to the point, in the style of a busy senior executive respecting their time. Ensure you include a Subject line.", 
    model=MODEL_NAME
)

# The Selector
selector = Agent(
    name="Email Selector",
    instructions="""You evaluate 3 email drafts and select the best one.
Imagine you are the target customer. Pick the email that is most persuasive, attractive, and likely to get a reply.
Do not provide any explanation, just return the exact content of the selected email.""",
    model=MODEL_NAME
)

# The Refiner
refiner = Agent(
    name="Email Refiner",
    instructions="""You polish and refine sales emails.
Take the provided email draft and improve its flow, fix any awkward phrasing, and ensure the Call-to-Action (CTA) is irresistible.
Output ONLY the final email content (Subject and Body). No intro or outro text.""",
    model=MODEL_NAME
)

# The Reply Handler
reply_handler = Agent(
    name="Reply Handler",
    instructions="""You analyze replies from prospective customers.
Identify their main objections, questions, or concerns. 
Summarize the sentiment and explicitly list what needs to be addressed in the follow-up email.""",
    model=MODEL_NAME
)

# ==========================================
# 3. LLM ORCHESTRATION (TOOLS)
# ==========================================

@function_tool
def send_email_tool(subject: str, text_body: str, html_body: str) -> str:
    """
    Send out the finalized sales email to the customer.
    
    Args:
        subject: The subject of the email
        text_body: The body of the email as plain text
        html_body: The HTML body of the email
    """
    send_email(subject, text_body, html_body)
    return "Email sent successfully via SMTP."

# Convert agents to tools so the Manager can orchestrate them
t_writer1 = writer1.as_tool("draft_professional_email", "Generate a professional email draft.")
t_writer2 = writer2.as_tool("draft_humorous_email", "Generate a humorous email draft.")
t_writer3 = writer3.as_tool("draft_executive_email", "Generate an executive style email draft.")
t_selector = selector.as_tool("select_best_email", "Pass all three drafts as input. This returns the best one.")
t_refiner = refiner.as_tool("refine_email", "Pass the selected draft to polish it for higher reply rates.")

manager_instructions = """
You are the Sales Manager at Asteral AI. Your job is to orchestrate the creation and sending of sales emails.

When asked to send an initial email or a follow-up:
1. Use all 3 writer tools (draft_professional_email, draft_humorous_email, draft_executive_email) to generate drafts. Pass the customer context to them.
2. Pass the 3 generated drafts to the select_best_email tool to pick the winner.
3. Pass the winning draft to the refine_email tool to polish it.
4. Finally, use the send_email_tool to send the polished email to the customer (ensure you separate Subject and Body appropriately).
"""

sales_manager = Agent(
    name="Sales Manager",
    instructions=manager_instructions,
    tools=[t_writer1, t_writer2, t_writer3, t_selector, t_refiner, send_email_tool],
    model=MODEL_NAME
)

# ==========================================
# 4. CODE ORCHESTRATION (THE ASYNC LOOP)
# ==========================================

async def main():
    print("--- Starting Multi-Agent Sales Cycle ---")
    
    # 1. Trigger the initial outreach
    initial_prompt = "Draft and send an initial cold sales email targeting a clothes shop owner. We want to sell them our smart clothes suggestion app."
    print("\n[Sales Cycle] Initiating first outreach...")
    await Runner.run(sales_manager, initial_prompt)
    
    # 2. Enter polling loop
    print("\n[Sales Cycle] Entering wait state. Polling inbox every 15 seconds for a reply...")
    
    while True:
        await asyncio.sleep(15)
        reply = check_for_replies()
        
        if reply:
            print(f"\n[Sales Cycle] >>> NEW REPLY RECEIVED! <<<")
            print(f"Subject: {reply['subject']}")
            print(f"Body: {reply['body']}\n")
            
            # Analyze the reply
            print("[Sales Cycle] Handing reply to the Reply Handler Agent...")
            analysis_result = await Runner.run(reply_handler, f"Analyze this customer reply:\nSubject:{reply['subject']}\nBody:{reply['body']}")
            analysis = analysis_result.final_output
            print(f"\n[Analysis]\n{analysis}\n")
            
            # Formulate the next action for the manager
            follow_up_prompt = f"""
We received a reply from the clothes shop owner. 
Here is the analysis of their reply:
{analysis}

Please generate 3 follow-up drafts addressing their concerns, select the best one, refine it, and send it back to them using the send_email_tool.
"""
            print("[Sales Cycle] Instructing Sales Manager to craft and send follow-up...")
            await Runner.run(sales_manager, follow_up_prompt)
            print("\n[Sales Cycle] Follow-up sent. Going back to polling state...")

if __name__ == "__main__":
    asyncio.run(main())
