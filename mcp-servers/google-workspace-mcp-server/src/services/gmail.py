"""Gmail service tools."""

import base64
import io
import logging
from typing import List

import dateparser
import pdfplumber
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

from ..auth import get_gmail_service

logger = logging.getLogger(__name__)


def extract_attachments_from_payload(payload: dict, attachments: list = None) -> list:
    """Recursively extract attachment metadata from email payload."""
    if attachments is None:
        attachments = []
    filename = payload.get('filename', '')
    if filename:
        body = payload.get('body', {})
        attachment_info = {
            'filename': filename,
            'mime_type': payload.get('mimeType', 'application/octet-stream'),
            'size': body.get('size', 0),
            'attachment_id': body.get('attachmentId', ''),
        }
        if attachment_info['mime_type'] == 'application/pdf':
            attachment_info['protection'] = 'unknown (check when downloading)'
        else:
            attachment_info['protection'] = 'none'
        attachments.append(attachment_info)
    if 'parts' in payload:
        for part in payload['parts']:
            extract_attachments_from_payload(part, attachments)
    return attachments


def extract_body_from_payload(payload: dict) -> tuple:
    """Recursively extract plain text and HTML body from email payload."""
    plain_text = ""
    html_text = ""
    mime_type = payload.get('mimeType', '')
    if 'body' in payload and 'data' in payload['body']:
        data = payload['body']['data']
        decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        if mime_type == 'text/plain':
            plain_text = decoded
        elif mime_type == 'text/html':
            html_text = decoded
    if 'parts' in payload:
        for part in payload['parts']:
            nested_plain, nested_html = extract_body_from_payload(part)
            if nested_plain and not plain_text:
                plain_text = nested_plain
            if nested_html and not html_text:
                html_text = nested_html
    return plain_text, html_text


def register_tools(mcp: FastMCP):
    """Register all Gmail tools on the shared MCP server."""

    # =========================================================================
    # EMAIL SEARCH & READ
    # =========================================================================

    @mcp.tool()
    def search_emails(
        query: str = "",
        sender: str = None,
        recipient: str = None,
        subject: str = None,
        start_date: str = None,
        end_date: str = None,
        max_results: int = 10
    ) -> str:
        """
        Search for emails in Gmail and return lightweight metadata (ID, subject, sender, date, snippet).
        Use get_email_content() to fetch full email body.

        Args:
            query: General search query (e.g., 'receipt').
            sender: Filter by sender (e.g., 'swiggy', 'uber'). Matches names or emails.
            recipient: Filter by recipient.
            subject: Filter by subject line.
            start_date: Start date (inclusive) in any common format (e.g., '2024-01-01', 'last week').
            end_date: End date (exclusive) in any common format.
            max_results: Maximum number of emails to return.
        """
        service = get_gmail_service()
        search_parts = []
        if query:
            search_parts.append(query)
        if sender:
            search_parts.append(f"from:{sender}")
        if recipient:
            search_parts.append(f"to:{recipient}")
        if subject:
            search_parts.append(f"subject:{subject}")
        if start_date:
            dt = dateparser.parse(start_date)
            if dt:
                search_parts.append(f"after:{dt.strftime('%Y/%m/%d')}")
        if end_date:
            dt = dateparser.parse(end_date)
            if dt:
                search_parts.append(f"before:{dt.strftime('%Y/%m/%d')}")
        final_query = " ".join(search_parts).strip()

        results = service.users().messages().list(userId='me', q=final_query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        if not messages:
            return "No messages found."
        output = []
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id'], format='metadata', metadataHeaders=['From', 'Subject', 'Date']).execute()
            headers = msg['payload']['headers']
            subject_val = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender_val = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            date_val = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown Date')
            snippet = msg.get('snippet', '')
            output.append(f"ID: {message['id']}\nDate: {date_val}\nFrom: {sender_val}\nSubject: {subject_val}\nSnippet: {snippet}\n---")
        return "\n".join(output)

    @mcp.tool()
    def get_email_content(email_id: str) -> str:
        """
        Get the full content of a specific email by ID, including attachment metadata.
        Use get_email_attachment() to download specific attachments.

        Args:
            email_id: The Gmail message ID (from search_emails results).
        """
        service = get_gmail_service()
        try:
            msg = service.users().messages().get(userId='me', id=email_id, format='full').execute()
            payload = msg['payload']
            headers = payload['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown Date')
            to = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown Recipient')
            plain_text, html_text = extract_body_from_payload(payload)
            if plain_text:
                body = plain_text
            elif html_text:
                soup = BeautifulSoup(html_text, 'html.parser')
                for element in soup(['script', 'style', 'head']):
                    element.decompose()
                body = soup.get_text(separator='\n', strip=True)
            else:
                body = msg.get('snippet', '(No body content available)')
            attachments = extract_attachments_from_payload(payload)
            if attachments:
                attachment_lines = [f"\n--- Attachments ({len(attachments)}) ---"]
                for i, att in enumerate(attachments, 1):
                    size_kb = att['size'] / 1024
                    size_str = f"{size_kb/1024:.1f}MB" if size_kb >= 1024 else f"{size_kb:.1f}KB"
                    attachment_lines.append(
                        f"{i}. {att['filename']} | {att['mime_type']} | {size_str} | protection: {att['protection']} | ID: {att['attachment_id']}"
                    )
                attachment_section = "\n".join(attachment_lines)
            else:
                attachment_section = "\n--- Attachments (0) ---\nNo attachments"
            return f"""Email ID: {email_id}
From: {sender}
To: {to}
Date: {date}
Subject: {subject}

--- Body ---
{body}
{attachment_section}"""
        except Exception as e:
            return f"Error fetching email {email_id}: {str(e)}"

    @mcp.tool()
    def get_email_attachment(email_id: str, attachment_id: str, password: str = None) -> str:
        """
        Download and read an email attachment. For PDFs, extracts text content.
        For other files, returns base64-encoded content.

        Args:
            email_id: The Gmail message ID.
            attachment_id: The attachment ID (from get_email_content results).
            password: Optional password for password-protected PDF files.
        """
        service = get_gmail_service()
        try:
            msg = service.users().messages().get(userId='me', id=email_id, format='full').execute()
            attachments = extract_attachments_from_payload(msg['payload'])
            attachment_info = None
            for att in attachments:
                if att['attachment_id'] == attachment_id:
                    attachment_info = att
                    break
            if not attachment_info and attachments and len(attachments) == 1:
                attachment_info = attachments[0]
                attachment_id = attachment_info['attachment_id']
            if not attachment_info:
                return f"Error: Attachment with ID {attachment_id} not found. Available: {[a['filename'] for a in attachments]}"

            filename = attachment_info['filename']
            mime_type = attachment_info['mime_type']
            attachment = service.users().messages().attachments().get(userId='me', messageId=email_id, id=attachment_id).execute()
            file_data = base64.urlsafe_b64decode(attachment['data'])

            if mime_type == 'application/pdf':
                try:
                    pdf_file = io.BytesIO(file_data)
                    pdf_password = password if password else None
                    text_content = []
                    with pdfplumber.open(pdf_file, password=pdf_password) as pdf:
                        for i, page in enumerate(pdf.pages, 1):
                            page_text = page.extract_text()
                            if page_text:
                                text_content.append(f"--- Page {i} ---\n{page_text}")
                    if text_content:
                        return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\n\n--- Extracted Text ---\n" + "\n\n".join(text_content)
                    else:
                        return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\n\nNote: PDF contains no extractable text."
                except Exception as pdf_error:
                    error_msg = str(pdf_error).lower()
                    if 'password' in error_msg or 'encrypted' in error_msg:
                        return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\nProtection: password-protected\n\nError: This PDF is password-protected. Provide the password parameter."
                    return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\n\nError extracting PDF: {str(pdf_error)}"
            elif mime_type.startswith('text/') or mime_type in ['application/json', 'application/xml']:
                try:
                    text_content = file_data.decode('utf-8', errors='ignore')
                    return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\n\n--- Content ---\n{text_content}"
                except Exception:
                    pass
            elif mime_type.startswith('image/'):
                b64_content = base64.b64encode(file_data).decode()
                return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\n\n--- Base64 Content ---\ndata:{mime_type};base64,{b64_content}"

            b64_content = base64.b64encode(file_data).decode()
            if len(b64_content) > 10000:
                return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\n\n--- Base64 (truncated) ---\n{b64_content[:10000]}..."
            return f"Attachment: {filename}\nType: {mime_type}\nSize: {len(file_data)} bytes\n\n--- Base64 Content ---\n{b64_content}"
        except Exception as e:
            return f"Error fetching attachment {attachment_id} from email {email_id}: {str(e)}"

    # =========================================================================
    # EMAIL SENDING
    # =========================================================================

    @mcp.tool()
    def send_email(
        to: str,
        subject: str,
        body: str,
        cc: str = None,
        bcc: str = None,
        reply_to_message_id: str = None,
        html: bool = False
    ) -> str:
        """
        Send an email or reply to an existing email thread.

        Args:
            to: Recipient email address(es), comma-separated for multiple.
            subject: Email subject line.
            body: Email body content.
            cc: CC recipient(s), comma-separated for multiple.
            bcc: BCC recipient(s), comma-separated for multiple.
            reply_to_message_id: Gmail message ID to reply to (for threading).
            html: If True, body is treated as HTML content.
        """
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        service = get_gmail_service()
        try:
            if html:
                message = MIMEMultipart('alternative')
                message.attach(MIMEText(body, 'html'))
            else:
                message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc

            thread_id = None
            if reply_to_message_id:
                original = service.users().messages().get(
                    userId='me', id=reply_to_message_id, format='metadata',
                    metadataHeaders=['Message-ID', 'References', 'Subject']
                ).execute()
                thread_id = original.get('threadId')
                headers = original['payload']['headers']
                original_message_id = next((h['value'] for h in headers if h['name'] == 'Message-ID'), None)
                references = next((h['value'] for h in headers if h['name'] == 'References'), '')
                if original_message_id:
                    message['In-Reply-To'] = original_message_id
                    message['References'] = f"{references} {original_message_id}".strip()

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            send_body = {'raw': raw_message}
            if thread_id:
                send_body['threadId'] = thread_id
            sent_message = service.users().messages().send(userId='me', body=send_body).execute()
            return f"""Email sent successfully!
Message ID: {sent_message['id']}
Thread ID: {sent_message.get('threadId', 'N/A')}
To: {to}
Subject: {subject}
{'(Reply to thread)' if reply_to_message_id else '(New conversation)'}"""
        except Exception as e:
            return f"Error sending email: {str(e)}"

    # =========================================================================
    # LABEL MANAGEMENT
    # =========================================================================

    @mcp.tool()
    def list_labels() -> str:
        """List all Gmail labels (both system and user-created). Returns label ID, name, and type for each label."""
        service = get_gmail_service()
        try:
            results = service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            if not labels:
                return "No labels found."
            system_labels = []
            user_labels = []
            for label in labels:
                label_info = f"ID: {label['id']} | Name: {label['name']} | Type: {label.get('type', 'user')}"
                if label.get('type') == 'system':
                    system_labels.append(label_info)
                else:
                    user_labels.append(label_info)
            output = ["--- System Labels ---"]
            output.extend(system_labels)
            output.append("\n--- User Labels ---")
            output.extend(user_labels if user_labels else ["(No custom labels)"])
            return "\n".join(output)
        except Exception as e:
            return f"Error listing labels: {str(e)}"

    @mcp.tool()
    def create_label(name: str, label_list_visibility: str = "labelShow", message_list_visibility: str = "show") -> str:
        """
        Create a new Gmail label.

        Args:
            name: The display name of the label (can include '/' for nested labels, e.g., 'Work/Projects').
            label_list_visibility: Visibility in label list - 'labelShow', 'labelShowIfUnread', or 'labelHide'.
            message_list_visibility: Visibility in message list - 'show' or 'hide'.
        """
        service = get_gmail_service()
        try:
            label_body = {'name': name, 'labelListVisibility': label_list_visibility, 'messageListVisibility': message_list_visibility}
            result = service.users().labels().create(userId='me', body=label_body).execute()
            return f"Label created successfully!\nID: {result['id']}\nName: {result['name']}\nType: {result.get('type', 'user')}"
        except Exception as e:
            return f"Error creating label '{name}': {str(e)}"

    @mcp.tool()
    def delete_label(label_id: str) -> str:
        """
        Delete a user-created label. System labels cannot be deleted.

        Args:
            label_id: The label ID (from list_labels). Use label ID, not label name.
        """
        service = get_gmail_service()
        try:
            service.users().labels().delete(userId='me', id=label_id).execute()
            return f"Label '{label_id}' deleted successfully."
        except Exception as e:
            return f"Error deleting label '{label_id}': {str(e)}"

    @mcp.tool()
    def get_label(label_id: str) -> str:
        """
        Get detailed information about a specific label including message counts.

        Args:
            label_id: The label ID (from list_labels).
        """
        service = get_gmail_service()
        try:
            label = service.users().labels().get(userId='me', id=label_id).execute()
            return f"""Label Details:
ID: {label['id']}
Name: {label['name']}
Type: {label.get('type', 'user')}
Message List Visibility: {label.get('messageListVisibility', 'N/A')}
Label List Visibility: {label.get('labelListVisibility', 'N/A')}
Messages Total: {label.get('messagesTotal', 0)}
Messages Unread: {label.get('messagesUnread', 0)}
Threads Total: {label.get('threadsTotal', 0)}
Threads Unread: {label.get('threadsUnread', 0)}"""
        except Exception as e:
            return f"Error getting label '{label_id}': {str(e)}"

    # =========================================================================
    # EMAIL MODIFICATION
    # =========================================================================

    @mcp.tool()
    def apply_labels(email_ids: List[str], label_ids: List[str]) -> str:
        """
        Apply one or more labels to one or more emails.

        Args:
            email_ids: List of email message IDs to modify.
            label_ids: List of label IDs to add (from list_labels).
        """
        service = get_gmail_service()
        try:
            results = []
            for email_id in email_ids:
                service.users().messages().modify(userId='me', id=email_id, body={'addLabelIds': label_ids}).execute()
                results.append(f"  {email_id}")
            return f"Labels {label_ids} applied to {len(results)} email(s):\n" + "\n".join(results)
        except Exception as e:
            return f"Error applying labels: {str(e)}"

    @mcp.tool()
    def remove_labels(email_ids: List[str], label_ids: List[str]) -> str:
        """
        Remove one or more labels from one or more emails.

        Args:
            email_ids: List of email message IDs to modify.
            label_ids: List of label IDs to remove (from list_labels).
        """
        service = get_gmail_service()
        try:
            results = []
            for email_id in email_ids:
                service.users().messages().modify(userId='me', id=email_id, body={'removeLabelIds': label_ids}).execute()
                results.append(f"  {email_id}")
            return f"Labels {label_ids} removed from {len(results)} email(s):\n" + "\n".join(results)
        except Exception as e:
            return f"Error removing labels: {str(e)}"

    def _modify_emails(email_ids: List[str], add_labels=None, remove_labels=None, action_name="modify"):
        """Helper for bulk email modification."""
        service = get_gmail_service()
        try:
            body = {}
            if add_labels:
                body['addLabelIds'] = add_labels
            if remove_labels:
                body['removeLabelIds'] = remove_labels
            for email_id in email_ids:
                service.users().messages().modify(userId='me', id=email_id, body=body).execute()
            return f"{action_name} {len(email_ids)} email(s)."
        except Exception as e:
            return f"Error: {str(e)}"

    @mcp.tool()
    def mark_as_read(email_ids: List[str]) -> str:
        """Mark one or more emails as read.

        Args:
            email_ids: List of email message IDs to mark as read.
        """
        return _modify_emails(email_ids, remove_labels=['UNREAD'], action_name="Marked as read")

    @mcp.tool()
    def mark_as_unread(email_ids: List[str]) -> str:
        """Mark one or more emails as unread.

        Args:
            email_ids: List of email message IDs to mark as unread.
        """
        return _modify_emails(email_ids, add_labels=['UNREAD'], action_name="Marked as unread")

    @mcp.tool()
    def archive_emails(email_ids: List[str]) -> str:
        """Archive one or more emails (remove from INBOX but keep in All Mail).

        Args:
            email_ids: List of email message IDs to archive.
        """
        return _modify_emails(email_ids, remove_labels=['INBOX'], action_name="Archived")

    @mcp.tool()
    def unarchive_emails(email_ids: List[str]) -> str:
        """Move archived emails back to INBOX.

        Args:
            email_ids: List of email message IDs to move back to inbox.
        """
        return _modify_emails(email_ids, add_labels=['INBOX'], action_name="Moved back to inbox")

    @mcp.tool()
    def trash_emails(email_ids: List[str]) -> str:
        """Move one or more emails to Trash.

        Args:
            email_ids: List of email message IDs to trash.
        """
        service = get_gmail_service()
        try:
            for email_id in email_ids:
                service.users().messages().trash(userId='me', id=email_id).execute()
            return f"Moved {len(email_ids)} email(s) to trash."
        except Exception as e:
            return f"Error trashing emails: {str(e)}"

    @mcp.tool()
    def untrash_emails(email_ids: List[str]) -> str:
        """Remove one or more emails from Trash.

        Args:
            email_ids: List of email message IDs to restore from trash.
        """
        service = get_gmail_service()
        try:
            for email_id in email_ids:
                service.users().messages().untrash(userId='me', id=email_id).execute()
            return f"Restored {len(email_ids)} email(s) from trash."
        except Exception as e:
            return f"Error restoring emails from trash: {str(e)}"

    @mcp.tool()
    def star_emails(email_ids: List[str]) -> str:
        """Star one or more emails.

        Args:
            email_ids: List of email message IDs to star.
        """
        return _modify_emails(email_ids, add_labels=['STARRED'], action_name="Starred")

    @mcp.tool()
    def unstar_emails(email_ids: List[str]) -> str:
        """Remove star from one or more emails.

        Args:
            email_ids: List of email message IDs to unstar.
        """
        return _modify_emails(email_ids, remove_labels=['STARRED'], action_name="Unstarred")

    @mcp.tool()
    def mark_as_important(email_ids: List[str]) -> str:
        """Mark one or more emails as important.

        Args:
            email_ids: List of email message IDs to mark as important.
        """
        return _modify_emails(email_ids, add_labels=['IMPORTANT'], action_name="Marked as important")

    @mcp.tool()
    def mark_as_not_important(email_ids: List[str]) -> str:
        """Remove important marker from one or more emails.

        Args:
            email_ids: List of email message IDs to mark as not important.
        """
        return _modify_emails(email_ids, remove_labels=['IMPORTANT'], action_name="Removed important marker from")

    # =========================================================================
    # FILTER MANAGEMENT
    # =========================================================================

    @mcp.tool()
    def list_filters() -> str:
        """List all Gmail filters configured for the account. Returns filter ID, criteria, and actions for each filter."""
        service = get_gmail_service()
        try:
            results = service.users().settings().filters().list(userId='me').execute()
            filters = results.get('filter', [])
            if not filters:
                return "No filters found."
            output = []
            for i, f in enumerate(filters, 1):
                criteria = f.get('criteria', {})
                action = f.get('action', {})
                criteria_parts = []
                if criteria.get('from'):
                    criteria_parts.append(f"From: {criteria['from']}")
                if criteria.get('to'):
                    criteria_parts.append(f"To: {criteria['to']}")
                if criteria.get('subject'):
                    criteria_parts.append(f"Subject: {criteria['subject']}")
                if criteria.get('query'):
                    criteria_parts.append(f"Query: {criteria['query']}")
                if criteria.get('hasAttachment'):
                    criteria_parts.append("Has attachment")
                action_parts = []
                if action.get('addLabelIds'):
                    action_parts.append(f"Add labels: {action['addLabelIds']}")
                if action.get('removeLabelIds'):
                    action_parts.append(f"Remove labels: {action['removeLabelIds']}")
                if action.get('forward'):
                    action_parts.append(f"Forward to: {action['forward']}")
                output.append(f"--- Filter {i} ---\nID: {f['id']}\nCriteria: {' AND '.join(criteria_parts) if criteria_parts else 'None'}\nActions: {', '.join(action_parts) if action_parts else 'None'}")
            return "\n\n".join(output)
        except Exception as e:
            return f"Error listing filters: {str(e)}"

    @mcp.tool()
    def create_filter(
        from_address: str = None,
        to_address: str = None,
        subject: str = None,
        query: str = None,
        has_attachment: bool = None,
        add_label_ids: List[str] = None,
        remove_label_ids: List[str] = None,
        mark_as_read: bool = False,
        archive: bool = False,
        star: bool = False,
        forward_to: str = None,
        never_spam: bool = False,
        mark_important: bool = None
    ) -> str:
        """
        Create a new Gmail filter rule to automatically process incoming emails.

        Args:
            from_address: Filter emails from this sender.
            to_address: Filter emails to this recipient.
            subject: Filter emails with this subject (supports partial match).
            query: Advanced Gmail search query for complex filtering.
            has_attachment: Filter emails with/without attachments.
            add_label_ids: List of label IDs to add to matching emails.
            remove_label_ids: List of label IDs to remove from matching emails.
            mark_as_read: Mark matching emails as read.
            archive: Archive matching emails (skip inbox).
            star: Star matching emails.
            forward_to: Email address to forward matching emails to.
            never_spam: Never mark matching emails as spam.
            mark_important: Mark matching emails as important (true) or not important (false).
        """
        service = get_gmail_service()
        try:
            criteria = {}
            if from_address:
                criteria['from'] = from_address
            if to_address:
                criteria['to'] = to_address
            if subject:
                criteria['subject'] = subject
            if query:
                criteria['query'] = query
            if has_attachment is not None:
                criteria['hasAttachment'] = has_attachment
            if not criteria:
                return "Error: At least one filter criteria must be specified."

            action = {}
            labels_to_add = list(add_label_ids) if add_label_ids else []
            if star:
                labels_to_add.append('STARRED')
            if mark_important is True:
                labels_to_add.append('IMPORTANT')
            if labels_to_add:
                action['addLabelIds'] = labels_to_add
            labels_to_remove = list(remove_label_ids) if remove_label_ids else []
            if mark_as_read:
                labels_to_remove.append('UNREAD')
            if archive:
                labels_to_remove.append('INBOX')
            if never_spam:
                labels_to_remove.append('SPAM')
            if mark_important is False:
                labels_to_remove.append('IMPORTANT')
            if labels_to_remove:
                action['removeLabelIds'] = labels_to_remove
            if forward_to:
                action['forward'] = forward_to
            if not action:
                return "Error: At least one filter action must be specified."

            result = service.users().settings().filters().create(userId='me', body={'criteria': criteria, 'action': action}).execute()
            return f"Filter created successfully!\nID: {result['id']}\nCriteria: {criteria}\nActions: {action}"
        except Exception as e:
            return f"Error creating filter: {str(e)}"

    @mcp.tool()
    def delete_filter(filter_id: str) -> str:
        """
        Delete a Gmail filter.

        Args:
            filter_id: The filter ID (from list_filters).
        """
        service = get_gmail_service()
        try:
            service.users().settings().filters().delete(userId='me', id=filter_id).execute()
            return f"Filter '{filter_id}' deleted successfully."
        except Exception as e:
            return f"Error deleting filter '{filter_id}': {str(e)}"

    @mcp.tool()
    def get_filter(filter_id: str) -> str:
        """
        Get detailed information about a specific filter.

        Args:
            filter_id: The filter ID (from list_filters).
        """
        service = get_gmail_service()
        try:
            f = service.users().settings().filters().get(userId='me', id=filter_id).execute()
            criteria = f.get('criteria', {})
            action = f.get('action', {})
            return f"""Filter Details:
ID: {f['id']}

Criteria:
  From: {criteria.get('from', 'Any')}
  To: {criteria.get('to', 'Any')}
  Subject: {criteria.get('subject', 'Any')}
  Query: {criteria.get('query', 'None')}
  Has Attachment: {criteria.get('hasAttachment', 'Any')}

Actions:
  Add Labels: {action.get('addLabelIds', [])}
  Remove Labels: {action.get('removeLabelIds', [])}
  Forward To: {action.get('forward', 'None')}"""
        except Exception as e:
            return f"Error getting filter '{filter_id}': {str(e)}"
