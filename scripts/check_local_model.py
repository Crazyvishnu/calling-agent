"""Optional live smoke check: python -m scripts.check_local_model (Ollama required)."""
import time
from backend.ai import OllamaProvider


def main():
    provider = OllamaProvider()
    history = [
        {'role': 'agent', 'message': "Hello! I'm Akki, an AI assistant for a website service. This is a consenting fictional local test. What should your website include?"},
        {'role': 'customer', 'message': 'I need a restaurant website with a menu, online booking and a gallery. My approximate budget is INR 12000. I would like it next month.'},
    ]
    started = time.monotonic()
    first = provider.reply(history, 'en-IN', {})
    draft = first.draft.model_dump(exclude_none=True, exclude_defaults=True)
    assert '12000' in (draft.get('budget') or ''), 'Budget extraction failed; choose another local model.'
    assert 'menu' in str(draft).lower(), 'Menu extraction failed; choose another local model.'
    assert 'next month' in (draft.get('timeline') or '').lower(), 'Timeline extraction failed.'
    assert first.draft.contact_person is None, 'Invented contact person.'
    assert first.draft.callback_time is None, 'Invented callback time.'
    print('First live turn passed in', round(time.monotonic() - started, 2), 'seconds', flush=True)
    print('Agent reply:', first.reply, flush=True)
    history += [{'role': 'agent', 'message': first.reply},
                {'role': 'customer', 'message': 'My preferred personal callback time is Friday at 4 pm.'}]
    started = time.monotonic()
    second = provider.reply(history, 'en-IN', draft)
    cumulative = dict(draft)
    cumulative.update(second.draft.model_dump(exclude_none=True, exclude_defaults=True))
    assert '12000' in (cumulative.get('budget') or ''), 'Conversation memory lost the budget.'
    assert 'friday' in (second.draft.callback_time or '').lower(), 'Callback preference extraction failed.'
    print('Second live turn passed in', round(time.monotonic() - started, 2), 'seconds', flush=True)
    print('Agent reply:', second.reply, flush=True)
    print('Fictional requirements draft:', cumulative)
    print('English smoke check only; no telephone or audio tested. Human review still required.')


if __name__ == '__main__':
    main()
