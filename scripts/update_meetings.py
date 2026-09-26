#!/usr/bin/env python3
"""Fetch official meeting sources, detect changes, and extract meeting candidates."""
from __future__ import annotations

import hashlib, html, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources.json"
STATE = ROOT / "data" / "source_state.json"
MEETINGS = ROOT / "data" / "meetings.json"
SNAPSHOTS = ROOT / "archive" / "source-snapshots"
USER_AGENT = "EdBeatWatch/1.1 (Massachusetts school committee public-meeting archive)"
ET = ZoneInfo("America/New_York")
MONTHS = {m.lower(): i for i, m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"],1)}
DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+(\d{1,2})(?:,\s*|\s+)(20\d{2})\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]\.?(?:m)\.?)\b", re.I)
LINK_RE = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I|re.S)
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept":"text/html,application/xhtml+xml"})
    with urlopen(req, timeout=45) as response:
        return response.read()


def textify(raw: str) -> str:
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.I|re.S)
    raw = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>", "\n", raw, flags=re.I)
    return re.sub(r"[ \t]+", " ", html.unescape(TAG_RE.sub(" ", raw)))


def parse_date(match):
    token = match.group(1).lower().rstrip(".")
    aliases={"jan":"january","feb":"february","mar":"march","apr":"april","jun":"june","jul":"july","aug":"august","sep":"september","sept":"september","oct":"october","nov":"november","dec":"december"}
    return datetime(int(match.group(3)), MONTHS[aliases.get(token, token)], int(match.group(2)), tzinfo=ET)


def extract_meetings(source: dict, body: bytes, checked: datetime) -> list[dict]:
    raw = body.decode("utf-8", "replace")
    text = textify(raw)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    links=[]
    for href,label in LINK_RE.findall(raw):
        label=" ".join(textify(label).split())
        if label: links.append((label, urljoin(source["url"], html.unescape(href))))
    today=checked.astimezone(ET).date()
    horizon=today+timedelta(days=45)
    out=[]
    for i,line in enumerate(lines):
        for dm in DATE_RE.finditer(line):
            dt=parse_date(dm)
            if not (today-timedelta(days=2) <= dt.date() <= horizon): continue
            context=" ".join(lines[max(0,i-2):min(len(lines),i+3)])
            low=context.lower()
            if not any(k in low for k in ("school committee","subcommittee","school board","meeting","agenda")): continue
            tm=TIME_RE.search(context)
            time_value=None
            if tm:
                hour=int(tm.group(1)); minute=int(tm.group(2) or 0); pm=tm.group(3).lower().startswith("p")
                hour=(hour%12)+(12 if pm else 0)
                time_value=f"{hour:02d}:{minute:02d}"
            related=[]
            for label,url in links:
                ll=label.lower()
                if any(k in ll for k in ("agenda","packet","meeting","notice","zoom","video","livestream")):
                    related.append({"label":label[:120],"url":url})
                if len(related)>=8: break
            title=context[:260]
            key=hashlib.sha1(f'{source["district"]}|{dt.date()}|{time_value}|{title}'.encode()).hexdigest()[:16]
            out.append({"id":key,"district":source["district"],"date":dt.date().isoformat(),"time":time_value,"title":title,"source_url":source["url"],"links":related,"discovered_at":checked.isoformat()})
    dedup={m["id"]:m for m in out}
    return list(dedup.values())


def main() -> None:
    registry=json.loads(SOURCES.read_text())
    old=json.loads(STATE.read_text()) if STATE.exists() else {"sources":{}}
    existing=json.loads(MEETINGS.read_text()) if MEETINGS.exists() else {"meetings":[]}
    old_meetings={m["id"]:m for m in existing.get("meetings",[]) if "id" in m}
    now=datetime.now(timezone.utc); stamp=now.strftime("%Y-%m-%dT%H-%M-%SZ")
    new_state={"checked_at":now.isoformat(),"sources":{}}; changed=[]; parsed=[]
    for source in registry["sources"]:
        district=source["district"]; key=district.lower().replace(" ","-")
        try:
            body=fetch(source["url"]); digest=hashlib.sha256(body).hexdigest(); previous=old.get("sources",{}).get(key,{}).get("sha256")
            is_changed=previous is not None and previous != digest
            folder=SNAPSHOTS/key; folder.mkdir(parents=True,exist_ok=True)
            if previous != digest: (folder/f"{stamp}.html").write_bytes(body)
            if is_changed: changed.append(district)
            parsed.extend(extract_meetings(source,body,now))
            new_state["sources"][key]={"district":district,"url":source["url"],"sha256":digest,"changed":is_changed,"last_checked":now.isoformat(),"error":None}
        except Exception as exc:
            prior=old.get("sources",{}).get(key,{})
            new_state["sources"][key]={**prior,"district":district,"url":source["url"],"changed":False,"last_checked":now.isoformat(),"error":str(exc)}
    for m in parsed:
        if m["id"] in old_meetings: m["discovered_at"]=old_meetings[m["id"]].get("discovered_at",m["discovered_at"])
        old_meetings[m["id"]]=m
    cutoff=(now.astimezone(ET).date()-timedelta(days=180)).isoformat()
    meetings=sorted((m for m in old_meetings.values() if m.get("date","")>=cutoff),key=lambda m:(m.get("date",""),m.get("time") or "99:99",m.get("district","")))
    STATE.write_text(json.dumps(new_state,indent=2)+"\n")
    MEETINGS.write_text(json.dumps({"generated_at":now.isoformat(),"timezone":"America/New_York","meetings":meetings},indent=2)+"\n")
    print(f"Checked {len(registry['sources'])} sources; parsed {len(parsed)} meeting candidates; changed: {', '.join(changed) or 'none'}")

if __name__ == "__main__": main()
