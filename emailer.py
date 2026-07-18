"""
emailer.py -- Sends an HTML alert email, with the listing photo embedded,
when a watchlist book matches a live listing.

Defaults to Gmail SMTP with an App Password (see README.md for how to
create one). To use a different provider, just change the host/port in
send_email() -- everything else (main.py, matcher.py) is unaffected.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import requests


def send_email(book_title, listing):
    sender = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    if not sender or not password:
        raise RuntimeError("EMAIL_ADDRESS / EMAIL_APP_PASSWORD are not set.")

    # EMAIL_TO may be a single address or a comma-separated list, e.g.
    # "me@example.com, partner@example.com" -- a GitHub secret is just one
    # string, so a comma-separated list is how multiple recipients fit in it.
    raw_recipients = os.environ.get("EMAIL_TO") or sender
    recipients = [addr.strip() for addr in raw_recipients.split(",") if addr.strip()]

    price = listing.get("price")
    currency = listing.get("currency", "")
    price_str = f"{price:.2f} {currency}".strip() if price is not None else "Not listed"

    msg = MIMEMultipart("related")
    msg["Subject"] = f"Match: {book_title} on {listing['source']} \u2014 {price_str}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    image_tag = (
        '<img src="cid:listing_image" style="max-width:420px;border-radius:6px;" />'
        if listing.get("image") else ""
    )
    url = listing.get("url", "")

    html = f"""
    <html>
      <body style="font-family: -apple-system, Arial, sans-serif; color: #222;">
        <h2 style="margin-bottom:0;">{listing.get('title', book_title)}</h2>
        <p style="color:#666;margin-top:4px;">Matched watchlist entry: <b>{book_title}</b></p>
        <p>
          <b>Source:</b> {listing['source']}<br>
          <b>Price:</b> {price_str}<br>
          <b>Link:</b> <a href="{url}">{url}</a>
        </p>
        {image_tag}
        <p style="margin-top:16px;white-space:pre-wrap;">{listing.get('description', '')}</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, "html"))

    if listing.get("image"):
        try:
            img_bytes = requests.get(listing["image"], timeout=15).content
            image = MIMEImage(img_bytes)
            image.add_header("Content-ID", "<listing_image>")
            image.add_header("Content-Disposition", "inline", filename="listing.jpg")
            msg.attach(image)
        except requests.RequestException:
            pass  # Email still sends fine without the embedded image.

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())
