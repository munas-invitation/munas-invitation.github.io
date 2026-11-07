"""RSVP health check for the invitation page.

Default (read-only): checks that the live page and the Google Form still match,
so a reply sent from the page lands in the sheet.

    python tests/check_rsvp.py            # read-only checks
    python tests/check_rsvp.py --submit   # also sends one test reply (adds a row to the sheet)
"""
import json
import re
import sys
import urllib.parse
import urllib.request

PAGE = "https://munas-invitation.github.io/"
FORM = "https://docs.google.com/forms/d/e/1FAIpQLSfiXgYUq1jjBjLDwWmbEs6wXe5fL4yMQQxoX7zdVJ1kog9tCQ/"
NAME_ENTRY = "122416638"
ATTEND_ENTRY = "568218989"
UA = {"User-Agent": "Mozilla/5.0 (invitation-rsvp-check)"}

failures = []


def check(ok, label):
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        failures.append(label)


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.geturl(), r.status, r.read().decode("utf-8", "replace")


# 1. The live page posts to this form with these fields.
_, status, page = get(PAGE)
check(status == 200, "invitation page loads")
check(FORM + "formResponse" in page or ("var FORM = '" + FORM + "'") in page, "page sends replies to the right form")
check("entry." + NAME_ENTRY in page, "page sends the name field")
check("entry." + ATTEND_ENTRY in page, "page sends the Yes/No field")
check("'Yes'" in page and "'No'" in page, "page sends Yes / No values")

# 2. The form is open to anyone and still has those fields.
final_url, status, form = get(FORM + "viewform")
check(status == 200 and "accounts.google.com" not in final_url, "form opens without signing in")
check("no longer accepting responses" not in form.lower(), "form is accepting responses")

m = re.search(r"FB_PUBLIC_LOAD_DATA_ = (.*?);\s*</script>", form, re.S)
check(m is not None, "form data readable")
if m:
    data = json.loads(m.group(1))
    questions = data[1][1]
    fields = {}
    for q in questions:
        for entry in (q[4] or []):
            options = [o[0] for o in (entry[1] or [])] if isinstance(entry[1], list) else []
            fields[str(entry[0])] = {"title": q[1], "required": entry[2] == 1, "options": options}
    check(NAME_ENTRY in fields, "form still has the name question")
    check(ATTEND_ENTRY in fields, "form still has the attend question")
    if ATTEND_ENTRY in fields:
        opts = fields[ATTEND_ENTRY]["options"]
        check("Yes" in opts and "No" in opts, "attend question still offers Yes and No (has %s)" % opts)
    extra = [f["title"] for k, f in fields.items() if f["required"] and k not in (NAME_ENTRY, ATTEND_ENTRY)]
    check(not extra, "no other required questions the page can't fill" + (" (found %s)" % extra if extra else ""))

# 3. Optional: send real test replies the same way the page does.
if "--submit" in sys.argv:
    for answer in ("Yes", "No"):
        body = urllib.parse.urlencode({
            "entry." + NAME_ENTRY: "Test %s (ignore)" % answer,
            "entry." + ATTEND_ENTRY: answer,
        }).encode()
        req = urllib.request.Request(FORM + "formResponse", data=body, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode("utf-8", "replace")
                ok = r.status == 200 and "response has been recorded" in text
        except urllib.error.HTTPError as e:
            ok = False
            print("      HTTP %s" % e.code)
        check(ok, "test %s reply accepted by the form" % answer)

print()
if failures:
    print("RSVP CHECK FAILED: %d problem(s)" % len(failures))
    sys.exit(1)
print("RSVP check passed")
