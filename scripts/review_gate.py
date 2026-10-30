"""Fail-closed CodeRabbit gate and exhaustive, commit-bound Reviewer certificate."""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "EnkiSolutions/journai"
BOT = "coderabbitai[bot]"


class GateError(Exception):
    pass


def token():
    value = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if value:
        return value
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    result = subprocess.run(
        ["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, env=env, check=False,
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if result.returncode or not values.get("password"):
        raise GateError("Authentification GitHub non interactive indisponible")
    return values["password"]


class GitHub:
    def __init__(self):
        self.credential = token()

    def request(self, path, method="GET", data=None):
        request = urllib.request.Request(
            "https://api.github.com" + path,
            data=None if data is None else json.dumps(data).encode(), method=method,
            headers={"Authorization": "Bearer " + self.credential,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            raise GateError(f"GitHub {method} {path}: HTTP {error.code}") from None

    def pages(self, path, key=None):
        result, page = [], 1
        while True:
            payload = self.request(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            items = payload[key] if key else payload
            result.extend(items)
            if len(items) < 100:
                return result
            page += 1

    def snapshot(self, number):
        prefix = f"/repos/{REPO}"
        pr = self.request(f"{prefix}/pulls/{number}")
        sha = pr["head"]["sha"]
        reviews = self.pages(f"{prefix}/pulls/{number}/reviews")
        checks = self.pages(f"{prefix}/commits/{sha}/check-runs", "check_runs")
        statuses = self.pages(f"{prefix}/commits/{sha}/statuses")
        files = self.pages(f"{prefix}/pulls/{number}/files")
        threads, cursor = [], None
        query = """query($owner:String!,$repo:String!,$number:Int!,$after:String){
          repository(owner:$owner,name:$repo){pullRequest(number:$number){
            reviewThreads(first:100,after:$after){pageInfo{hasNextPage endCursor}
              nodes{isResolved comments(first:1){nodes{author{login}}}}}}}}"""
        while True:
            payload = self.request("/graphql", "POST", {"query": query, "variables": {
                "owner": "EnkiSolutions", "repo": "journai", "number": number, "after": cursor}})
            if payload.get("errors"):
                raise GateError("Impossible de vérifier les fils CodeRabbit")
            block = payload["data"]["repository"]["pullRequest"]["reviewThreads"]
            threads.extend(block["nodes"])
            if not block["pageInfo"]["hasNextPage"]:
                break
            cursor = block["pageInfo"]["endCursor"]
        return dict(pr=pr, reviews=reviews, checks=checks, statuses=statuses, files=files, threads=threads)


def changed_lines(files):
    expected, unpatchable = set(), set()
    for file in files:
        patch, path = file.get("patch"), file["filename"]
        if patch is None:
            unpatchable.add(path)
            continue
        old = new = 0
        count = 0
        for line in patch.splitlines():
            hunk = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if hunk:
                old, new = map(int, hunk.groups())
            elif line.startswith("+"):
                expected.add((path, "RIGHT", new)); new += 1; count += 1
            elif line.startswith("-"):
                expected.add((path, "LEFT", old)); old += 1; count += 1
            elif line.startswith(" "):
                old += 1; new += 1
        if count != file["additions"] + file["deletions"]:
            raise GateError(f"Diff tronqué ou incomplet : {path}. Scinder la PR pour permettre une revue exhaustive.")
    return expected, unpatchable


def evaluate(snapshot, certificate=None):
    pr = snapshot["pr"]
    sha = pr["head"]["sha"]
    if pr["state"] != "open" or pr.get("draft"):
        raise GateError("La PR doit être ouverte et prête à relire")
    reviews = [r for r in snapshot["reviews"] if r["user"].get("login") == BOT
               and r["user"].get("type") == "Bot" and r["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")]
    latest = max(reviews, key=lambda r: r["id"], default=None)
    if not latest or latest["state"] != "APPROVED" or latest["commit_id"] != sha:
        raise GateError("CodeRabbit doit approuver le SHA courant ; revue absente, périmée ou corrections demandées")
    for thread in snapshot["threads"]:
        author = thread["comments"]["nodes"][0].get("author") if thread["comments"]["nodes"] else None
        if author and author.get("login") in (BOT, "coderabbitai") and not thread["isResolved"]:
            raise GateError("Un fil CodeRabbit reste ouvert")
    latest_checks = {}
    for check in sorted(snapshot["checks"], key=lambda c: c["id"]):
        latest_checks[(check["name"], check.get("app", {}).get("id"))] = check
    bot_checks = [c for c in latest_checks.values() if c["name"] == "CodeRabbit"
                  and c.get("app", {}).get("slug", "").startswith("coderabbit")]
    if not bot_checks or any(c["status"] != "completed" or c["conclusion"] != "success" for c in bot_checks):
        raise GateError("Contrôle CodeRabbit du dernier SHA absent ou non réussi")
    for check in latest_checks.values():
        if check["status"] != "completed" or check["conclusion"] not in ("success", "neutral", "skipped"):
            raise GateError(f"Contrôle incomplet ou en échec : {check['name']}")
    statuses = {}
    for status in snapshot["statuses"]:  # GitHub returns newest first.
        statuses.setdefault(status["context"], status)
    for name, status in statuses.items():
        if name != "JournAI Reviewer" and status["state"] != "success":
            raise GateError(f"Statut incomplet ou en échec : {name}")
    if certificate is None:
        return sha
    if certificate.get("head_sha") != sha or certificate.get("decision") != "approve":
        raise GateError("Le certificat doit approuver exactement le SHA courant")
    if not str(certificate.get("summary", "")).strip() or not certificate.get("validation"):
        raise GateError("Résumé et preuves de validation obligatoires")
    expected, unpatchable = changed_lines(snapshot["files"])
    actual = []
    for item in certificate.get("lines", []):
        if not isinstance(item.get("line"), int) or len(str(item.get("reason", "")).strip()) < 20:
            raise GateError("Chaque ligne exige un numéro et une justification précise")
        actual.append((item.get("path"), item.get("side"), item["line"]))
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise GateError(f"Couverture non exhaustive : {len(expected - set(actual))} lignes manquantes, {len(set(actual) - expected)} étrangères ou doublons")
    binary = certificate.get("binary_files", [])
    if {b.get("path") for b in binary} != unpatchable or any(len(str(b.get("reason", "")).strip()) < 20 for b in binary):
        raise GateError("Justification obligatoire pour chaque fichier sans patch textuel")
    return sha


def certificate_parts(certificate, budget=50000):
    """Keep large line-by-line reviews usable without truncating evidence."""
    parts, current = [], []
    for line in certificate.get("lines", []):
        candidate = current + [line]
        if len(json.dumps(candidate, ensure_ascii=False).encode()) > budget:
            if not current:
                raise GateError("Une justification dépasse la taille maximale d’un commentaire")
            parts.append(current)
            current = [line]
            if len(json.dumps(current, ensure_ascii=False).encode()) > budget:
                raise GateError("Une justification dépasse la taille maximale d’un commentaire")
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--certificate")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    if (args.publish or args.merge) and not args.certificate:
        parser.error("--publish et --merge exigent --certificate")
    github = GitHub()
    certificate = None
    if args.certificate:
        with open(args.certificate, encoding="utf8") as stream:
            certificate = json.load(stream)
    snapshot = github.snapshot(args.pr)
    sha = evaluate(snapshot, certificate)
    prefix = f"/repos/{REPO}"
    if args.publish or args.merge:
        parts = certificate_parts(certificate)
        index = {key: value for key, value in certificate.items() if key != "lines"}
        index["line_count"] = len(certificate.get("lines", []))
        index["line_justification_comments"] = []
        # Validate the index size before publishing any part.
        if len(json.dumps(index, ensure_ascii=False).encode()) > 45000:
            raise GateError("Résumé de certificat trop volumineux")
        for number, lines in enumerate(parts, 1):
            part = {"head_sha": sha, "part": number, "total_parts": len(parts), "lines": lines}
            evidence = github.request(f"{prefix}/issues/{args.pr}/comments", "POST", {
                "body": "## Reviewer JournAI — justification des lignes\n\n```json\n" + json.dumps(part, ensure_ascii=False) + "\n```"})
            index["line_justification_comments"].append(evidence["html_url"])
        body = "## Validation du Reviewer JournAI\n\nModèle : GPT-6.1 Sol xHigh, harness Pi.\n\n```json\n" + json.dumps(index, ensure_ascii=False, indent=2) + "\n```"
        if len(body.encode()) > 60000:
            raise GateError("Index de certificat trop volumineux")
        if evaluate(github.snapshot(args.pr), certificate) != sha:
            raise GateError("Le SHA a changé pendant la publication du certificat")
        comment = github.request(f"{prefix}/issues/{args.pr}/comments", "POST", {"body": body})
        github.request(f"{prefix}/statuses/{sha}", "POST", {
            "state": "success", "context": "JournAI Reviewer", "target_url": comment["html_url"],
            "description": "Chaque ligne justifiée ; certificat lié au SHA et CodeRabbit vérifié"})
    if args.merge:
        # Re-fetch after publication; the merge endpoint also checks the SHA atomically.
        if evaluate(github.snapshot(args.pr), certificate) != sha:
            raise GateError("Le SHA a changé")
        result = github.request(f"{prefix}/pulls/{args.pr}/merge", "PUT", {
            "sha": sha, "merge_method": "squash"})
        if not result.get("merged"):
            raise GateError("GitHub n’a pas confirmé la fusion")
    print(json.dumps({"ok": True, "head_sha": sha, "certificate": certificate is not None, "merged": args.merge}))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf8")
    try:
        main()
    except (GateError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
