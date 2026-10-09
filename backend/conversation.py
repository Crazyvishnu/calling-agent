"""Explicitly scripted demo agent, not an LLM or a real telephone call."""
import re

HELLO = (
    "Hello! I'm Akki, an AI assistant for a website design service. "
    "This is a demonstration conversation, not a phone call. "
    "Would you be interested in discussing a website for your business?"
)


def decline_changes(message: str) -> dict:
    """Conservative prototype suppression. A model may additionally detect intent."""
    lower = message.casefold().strip().rstrip('.!?।')
    if any(word in lower for word in ('stop calling', 'do not call', "don't call", 'remove my number', 'unsubscribe',
                                      'कॉल मत', 'फोन मत', 'కాల్ చేయవద్దు', 'ఫోన్ చేయవద్దు')) or lower in ('stop', 'opt out'):
        return {'do_not_call': True, 'contact_allowed': False, 'status': 'not_interested'}
    if lower in ('no', 'nope', 'नहीं', 'వద్దు') or any(word in lower for word in (
            'not interested', 'no thanks', 'no thank you', "don't need", 'do not need',
            'दिलचस्पी नहीं', 'ఆసక్తి లేదు')):
        return {'status': 'not_interested', 'contact_allowed': False}
    return {}


def respond(message: str, lead: dict, customer_messages: list[str]) -> tuple[str, dict]:
    """Return next scripted response and extracted lead fields."""
    lower = message.lower().strip()
    changes: dict = {}

    declined = decline_changes(message)
    if declined:
        return "Understood. We have disabled further outreach. Thank you for your time!", declined

    money = re.search(r'(?:₹|rs\.?\s*|inr\s*)([\d,]+)(?:\s*(?:to|-)\s*(?:₹|rs\.?\s*)?([\d,]+))?', lower)
    if money:
        changes['budget'] = '₹' + money.group(1).replace(',', '')
        if money.group(2):
            changes['budget'] += '–₹' + money.group(2).replace(',', '')
    elif 'budget' in lower:
        numbers = re.findall(r'\b\d{4,7}\b', lower)
        if numbers:
            changes['budget'] = '₹' + '–₹'.join(numbers[:2])

    feature_terms = {
        'online booking': ('booking', 'reservation', 'appointment'),
        'online payments': ('payment', 'pay online'),
        'menu': ('menu',),
        'product catalog': ('catalog', 'products', 'product listing'),
        'online store': ('ecommerce', 'e-commerce', 'online store'),
        'contact page': ('contact page', 'contact form'),
        'gallery': ('gallery', 'photos'),
        'WhatsApp button': ('whatsapp',),
    }
    matched = [name for name, keywords in feature_terms.items() if any(k in lower for k in keywords)]
    if matched:
        existing = [x.strip() for x in lead.get('requirements', '').split(',') if x.strip()]
        changes['requirements'] = ', '.join(dict.fromkeys(existing + matched))
    if any(term in lower for term in ('next week', 'next month', 'this week', 'urgent', 'asap', 'two weeks')):
        changes['timeline'] = next(term for term in ('asap', 'urgent', 'this week', 'next week', 'two weeks', 'next month') if term in lower)

    if re.search(r'\b(?:yes|interested|need website|want website|new website|redesign)\b', lower) or matched or money:
        changes['status'] = 'interested'

    count = len(customer_messages)
    if count == 1:
        if changes.get('status') == 'interested':
            reply = 'Great! What should your website include? For example: a menu, bookings, product catalog or contact form.'
        else:
            reply = 'Would a simple business website be useful? You can also say no thanks.'
    elif count == 2:
        reply = 'Thanks! Do you have an approximate budget in rupees and a preferred timeline?'
    elif count == 3:
        reply = 'Got it. Would you prefer a personal follow-up to discuss the details?'
    else:
        reply = 'Thank you! I have noted your answers for review. A person will only follow up if you have agreed to be contacted.'
    return reply, changes
