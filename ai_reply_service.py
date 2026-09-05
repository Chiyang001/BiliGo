"""Shared AI reply configuration helpers for every supported platform."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests

from app_paths import get_app_root
from ai_conversation_store import ai_conversation_store


AI_PLATFORM_KEYS = ('bili_message', 'bili_comment', 'xiaohongshu', 'weibo', 'douyin', 'xianyu')
DEFAULT_MODEL_SETTINGS = {'context_enabled': True, 'context_window': 6000, 'auto_compress': True, 'prohibited_words': []}
DEFAULT_HANDOFF_SETTINGS = {'enabled': False}
PROHIBITED_MESSAGE_REPLY = '您发送的消息含有敏感或违禁词'

def normalize_model_settings(value: Any) -> Dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_MODEL_SETTINGS)
    result['context_enabled'] = bool(value.get('context_enabled', True))
    try:
        result['context_window'] = max(500, min(128000, int(value.get('context_window', 6000))))
    except (TypeError, ValueError):
        result['context_window'] = 6000
    result['auto_compress'] = bool(value.get('auto_compress', True))
    def split_words(raw: Any) -> list[str]:
        values = [raw] if isinstance(raw, str) else list(raw or [])
        return [
            part.strip()
            for item in values
            for part in re.split(r'[,，]', str(item))
            if part.strip()
        ]

    raw = split_words(value.get('prohibited_words', []))
    # 旧版“敏感词”设置迁移到违禁词，避免升级后已有拦截规则静默丢失。
    legacy_sensitive = split_words(value.get('sensitive_words', []))
    combined = raw + legacy_sensitive
    result['prohibited_words'] = list(dict.fromkeys(
        str(item).strip() for item in combined if str(item).strip()
    ))[:500]
    return result


def normalize_platforms(value: Any) -> Dict[str, bool]:
    value = value if isinstance(value, dict) else {}
    return {key: bool(value.get(key, False)) for key in AI_PLATFORM_KEYS}


def normalize_handoff_settings(value: Any) -> Dict[str, bool]:
    value = value if isinstance(value, dict) else {}
    return {'enabled': bool(value.get('enabled', False))}


def load_app_config() -> Dict[str, Any]:
    try:
        with open(os.path.join(get_app_root(), 'config.json'), 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return {}


def load_provider() -> Dict[str, Any]:
    return load_app_config().get('ai_provider') or {}


def platform_enabled(platform: str, provider: Optional[Dict[str, Any]] = None) -> bool:
    provider = provider or load_provider()
    return bool(provider.get('enabled') and normalize_platforms(provider.get('platforms')).get(platform))


def normalize_knowledge_config(value: Any) -> Dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    bases = value.get('bases') if isinstance(value.get('bases'), list) else []
    assignments = value.get('platform_assignments') if isinstance(value.get('platform_assignments'), dict) else {}
    # Migrate the original single knowledge base in memory without losing user data.
    if not bases and (value.get('text') or value.get('documents')):
        bases = [{
            'id': 'legacy_default', 'name': '默认知识库',
            'text': str(value.get('text') or ''), 'documents': list(value.get('documents') or []),
        }]
        assignments = {key: ['legacy_default'] for key in AI_PLATFORM_KEYS}
    normalized_bases = []
    for base in bases:
        if not isinstance(base, dict) or not str(base.get('id') or ''):
            continue
        normalized_bases.append({
            'id': str(base.get('id')), 'name': str(base.get('name') or '未命名知识库'),
            'text': str(base.get('text') or ''), 'documents': list(base.get('documents') or []),
        })
    valid_ids = {base['id'] for base in normalized_bases}
    normalized_assignments = {
        key: [str(item) for item in (assignments.get(key) or []) if str(item) in valid_ids]
        for key in AI_PLATFORM_KEYS
    }
    return {'enabled': bool(value.get('enabled', False)), 'bases': normalized_bases, 'platform_assignments': normalized_assignments}


def build_knowledge_context(knowledge: Optional[Dict[str, Any]] = None, platform: Optional[str] = None) -> str:
    if knowledge is None:
        knowledge = load_app_config().get('ai_knowledge_base') or {}
    knowledge = normalize_knowledge_config(knowledge)
    if not knowledge['enabled']:
        return ''
    chunks = []
    selected_ids = set(knowledge['platform_assignments'].get(platform, [])) if platform else {base['id'] for base in knowledge['bases']}
    knowledge_root = os.path.abspath(os.path.join(get_app_root(), 'ai_knowledge'))
    for base in knowledge['bases']:
        if base['id'] not in selected_ids:
            continue
        base_chunks = []
        text = base['text'].strip()
        if text:
            base_chunks.append(text[:20000])
        for document in base['documents']:
            if document.get('content_in_text'):
                continue
            path = os.path.abspath(str(document.get('path') or ''))
            try:
                if os.path.commonpath([knowledge_root, path]) != knowledge_root:
                    continue
                with open(path, 'r', encoding='utf-8') as handle:
                    content = handle.read(20000).strip()
                if content:
                    base_chunks.append(f"文档：{document.get('name') or os.path.basename(path)}\n{content}")
            except (OSError, ValueError):
                continue
        if base_chunks:
            chunks.append(f"知识库：{base['name']}\n" + '\n\n'.join(base_chunks))
        if sum(len(chunk) for chunk in chunks) >= 60000:
            break
    if not chunks:
        return ''
    return '请优先依据以下知识库回答。知识库没有相关信息时，再使用通用知识。\n\n' + '\n\n---\n\n'.join(chunks)


def build_conversation_context(
    platform: str, contact_id: str, provider: Optional[Dict[str, Any]] = None,
) -> str:
    """Return recent, successful exchanges for one contact on one platform."""
    provider = provider or load_provider()
    settings = normalize_model_settings(provider.get('model_settings'))
    if not settings['context_enabled']:
        return ''
    # Leave room for the current message, instructions and assigned knowledge base.
    history_budget = max(250, min(60000, int(settings['context_window'] * 0.6)))
    return ai_conversation_store.build_context(platform, str(contact_id or ''), history_budget)


def record_conversation_exchange(
    platform: str, contact_id: str, user_message: str, assistant_message: str,
    event_key: str, provider: Optional[Dict[str, Any]] = None,
) -> bool:
    """Persist an exchange only while context is enabled and delivery succeeded."""
    provider = provider or load_provider()
    settings = normalize_model_settings(provider.get('model_settings'))
    if not settings['context_enabled']:
        return False
    return ai_conversation_store.record_exchange(
        platform, str(contact_id or ''), user_message, assistant_message, event_key,
    )


def _request_completion(provider: Dict[str, Any], prompt: str, max_tokens: int = 256) -> Optional[str]:
    fmt = provider.get('format', 'openai')
    base_url = str(provider.get('base_url', '')).rstrip('/')
    model = provider.get('model', '')
    try:
        if fmt == 'anthropic':
            url = base_url if base_url.endswith('/messages') else base_url + '/messages'
            response = requests.post(
                url,
                headers={'x-api-key': provider['api_key'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                json={'model': model, 'max_tokens': max_tokens, 'messages': [{'role': 'user', 'content': prompt}]},
                timeout=20,
            )
            body = response.json()
            return (body.get('content') or [{}])[0].get('text') if response.ok else None
        url = base_url if base_url.endswith('/chat/completions') else base_url + '/chat/completions'
        response = requests.post(
            url,
            headers={'Authorization': f"Bearer {provider['api_key']}", 'Content-Type': 'application/json'},
            json={'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': max_tokens},
            timeout=20,
        )
        body = response.json()
        return ((body.get('choices') or [{}])[0].get('message') or {}).get('content') if response.ok else None
    except (requests.RequestException, ValueError, IndexError, TypeError):
        return None


def _prepare_prompt(
    message: str, context: str, provider: Dict[str, Any],
    knowledge: Optional[Dict[str, Any]], platform: Optional[str],
) -> tuple[str, Dict[str, Any]]:
    settings = normalize_model_settings(provider.get('model_settings'))
    knowledge_context = build_knowledge_context(knowledge, platform) if settings['context_enabled'] else ''
    # Put recent conversation immediately before the current message. When automatic
    # compression keeps the tail, user history survives ahead of less relevant knowledge.
    prompt = '\n\n'.join(part for part in (knowledge_context, context, f'用户消息：{message}') if part).strip()
    if not settings['context_enabled']:
        prompt = f'用户消息：{message}'
    if len(prompt) > settings['context_window']:
        prompt = prompt[-settings['context_window']:] if settings['auto_compress'] else prompt[:settings['context_window']]
    restrictions = settings['prohibited_words']
    if restrictions:
        prompt += '\n\n请勿输出或复述以下词语：' + '、'.join(restrictions)
    return prompt, settings


def prohibited_message_reply(message: str, provider: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return the fixed reply when an incoming message contains a configured prohibited word."""
    provider = provider or load_provider()
    message_folded = str(message or '').casefold()
    if not message_folded:
        return None
    settings = normalize_model_settings(provider.get('model_settings'))
    for word in settings['prohibited_words']:
        if word.casefold() in message_folded:
            return PROHIBITED_MESSAGE_REPLY
    return None


def generate_reply(message: str, context: str = '', provider: Optional[Dict[str, Any]] = None,
                   knowledge: Optional[Dict[str, Any]] = None, platform: Optional[str] = None) -> Optional[str]:
    provider = provider or load_provider()
    prohibited_reply = prohibited_message_reply(message, provider)
    if prohibited_reply:
        return prohibited_reply
    if not provider.get('enabled') or not provider.get('api_key'):
        return None
    prompt, _ = _prepare_prompt(message, context, provider, knowledge, platform)
    return _request_completion(provider, prompt, max_tokens=256)


def generate_reply_decision(
    message: str, context: str = '', provider: Optional[Dict[str, Any]] = None,
    knowledge: Optional[Dict[str, Any]] = None, platform: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a reply or explicitly route the message to a human queue."""
    provider = provider or load_provider()
    prohibited_reply = prohibited_message_reply(message, provider)
    if prohibited_reply:
        return {'needs_human': False, 'reason': '', 'reply': prohibited_reply}
    handoff = normalize_handoff_settings(provider.get('human_handoff'))
    if not handoff['enabled']:
        return {'needs_human': False, 'reason': '', 'reply': generate_reply(message, context, provider, knowledge, platform)}
    if not provider.get('enabled') or not provider.get('api_key'):
        return {'needs_human': True, 'reason': 'AI 服务当前不可用', 'reply': None}

    base_prompt, _ = _prepare_prompt(message, context, provider, knowledge, platform)
    instruction = (
        '你同时负责客服回复和人工升级判断。仅在以下情况标记为需要人工：'
        '缺少可靠信息且无法安全回答；知识库无法支持具体业务结论；涉及退款、支付、订单、账号权限、'
        '投诉争议、法律或隐私；用户明确要求人工；继续自动回答可能误导用户。'
        '普通问候、常规咨询和能够依据知识库回答的问题不要升级。'
        '只输出一个 JSON 对象，不要使用 Markdown：'
        '{"needs_human":false,"reason":"","reply":"给用户的回复"}。'
        '需要人工时 reply 必须为空，并用一句简短中文说明原因。'
    )
    raw = _request_completion(provider, instruction + '\n\n' + base_prompt, max_tokens=384)
    if not raw:
        return {'needs_human': True, 'reason': 'AI 未能生成可靠回复', 'reply': None}
    cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(raw).strip(), flags=re.I)
    match = re.search(r'\{.*\}', cleaned, flags=re.S)
    try:
        parsed = json.loads(match.group(0) if match else cleaned)
    except (ValueError, TypeError, AttributeError):
        # Compatible fallback for models that ignore the JSON-only instruction.
        return {'needs_human': False, 'reason': '', 'reply': cleaned.strip() or None}
    needs_human = parsed.get('needs_human') is True or str(parsed.get('needs_human', '')).lower() == 'true'
    reason = str(parsed.get('reason') or '').strip()[:240]
    reply = str(parsed.get('reply') or '').strip()
    if needs_human or not reply:
        return {'needs_human': True, 'reason': reason or 'AI 无法确认可靠回复', 'reply': None}
    return {'needs_human': False, 'reason': '', 'reply': reply}
