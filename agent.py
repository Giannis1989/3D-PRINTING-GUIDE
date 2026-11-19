import os
import re
import glob
import time
from github import Github
from google import genai

g = Github(os.environ["GITHUB_TOKEN"])
repo = g.get_repo(os.environ["REPO_NAME"])
issue = repo.get_issue(number=int(os.environ["ISSUE_NUMBER"]))

files_dict = {}
guide_content = ""
for filepath in sorted(glob.glob("**/*.md", recursive=True)):
    with open(filepath, "r", encoding="utf-8") as file:
        content = file.read()
        files_dict[filepath] = content
        guide_content += f"\n--- Αρχείο: {filepath} ---\n{content}"

comments = list(issue.get_comments())
user_query = comments[-1].body.strip() if comments else f"{issue.title}\n{issue.body}".strip()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

available_models = [
    m.name.replace("models/", "") for m in client.models.list()
    if "gemini" in m.name and not any(x in m.name for x in ["embedding", "imagen", "veo"])
]

def ask_gemini(prompt_text):
    for model_name in available_models:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt_text)
            if res.text:
                return res.text
        except Exception:
            continue
    raise RuntimeError("Δεν βρέθηκε ενεργό μοντέλο Gemini.")

def clean_markdown(text):
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n", "", text)
    text = re.sub(r"\n```$", "", text)
    return text.strip()

command_prefixes = ("/add", "/edit", "/remove")

if user_query.startswith(command_prefixes):
    for prefix in command_prefixes:
        if user_query.startswith(prefix):
            task = user_query[len(prefix):].strip()
            action_type = prefix
            break

    prompt = f"""
    Είσαι ο αρχισυντάκτης ενός κορυφαίου οδηγού 3D Printing (FDM) στα Ελληνικά.
    Ο διαχειριστής σου έδωσε την εντολή ({action_type}): "{task}"

    Διάβασε όλα τα υπάρχοντα αρχεία του οδηγού:
    {guide_content}

    ΟΔΗΓΙΕΣ:
    - Μπορείς να τροποποιήσεις, να δημιουργήσεις ή να διαγράψεις ΕΝΑ ή ΠΟΛΛΑ αρχεία (π.χ. να προσθέσεις ενότητα σε ένα αρχείο και ταυτόχρονα να ενημερώσεις τον πίνακα περιεχομένων στο README.md).
    - Διατήρησε απαρέγκλιτα το ύφος, τη δομή και το υπάρχον περιεχόμενο των αρχείων (εκτός αν σου ζητήθηκε αφαίρεση/αλλαγή).
    - Απάντησε ΑΥΣΤΗΡΑ χρησιμοποιώντας το παρακάτω μπλοκ για ΚΑΘΕ αρχείο που αλλάζει:

    ===FILE: <ακριβές όνομα αρχείου, π.χ. 02-ylika-akrofysia.md ή README.md>===
    ACTION: <UPDATE ή CREATE ή DELETE>
    CONTENT:
    <ολόκληρο το τελικό περιεχόμενο του αρχείου σε καθαρό Markdown - άφησέ το κενό μόνο αν ACTION είναι DELETE>
    ===END_FILE===
    """

    result = ask_gemini(prompt).strip()
    file_blocks = re.findall(r"===FILE:\s*(.+?)\s*===\s*ACTION:\s*(UPDATE|CREATE|DELETE)\s*CONTENT:\n?(.*?)\s*===END_FILE===", result, re.DOTALL)

    if not file_blocks:
        issue.create_comment("Δεν μπόρεσα να επεξεργαστώ τη δομή των αλλαγών. Δοκίμασε να διατυπώσεις την εντολή λίγο πιο συγκεκριμένα.")
    else:
        branch_name = f"ai-update-{issue.number}-{int(time.time())}"
        main_ref = repo.get_git_ref("heads/main")
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=main_ref.object.sha)

        modified_files = []

        for target_file, action, raw_content in file_blocks:
            target_file = target_file.strip()
            new_content = clean_markdown(raw_content)

            if action == "DELETE" and target_file in files_dict:
                existing_file = repo.get_contents(target_file, ref="main")
                repo.delete_file(target_file, f"AI διαγραφή αρχείου (#{issue.number})", existing_file.sha, branch=branch_name)
                modified_files.append(f"`{target_file}` (Διαγραφή)")
            elif target_file in files_dict:
                existing_file = repo.get_contents(target_file, ref="main")
                repo.update_file(target_file, f"AI ενημέρωση ({action_type}) (#{issue.number})", new_content, existing_file.sha, branch=branch_name)
                modified_files.append(f"`{target_file}`")
            else:
                repo.create_file(target_file, f"AI νέο αρχείο ({action_type}) (#{issue.number})", new_content, branch=branch_name)
                modified_files.append(f"`{target_file}` (Νέο)")

        files_list_str = ", ".join(modified_files)
        pr = repo.create_pull(
            title=f"AI {action_type}: {task[:55]}",
            body=f"Αυτόματη ενημέρωση από το Issue #{issue.number}.\n\n**Αρχεία που τροποποιήθηκαν:** {files_list_str}",
            head=branch_name,
            base="main"
        )
        issue.create_comment(f"Έτοιμες οι αλλαγές στα αρχεία: {files_list_str}!\n\nΈλεγξε και κάνε Merge το Pull Request εδώ: {pr.html_url}")

else:
    prompt = f"""
    Είσαι ένας εξειδικευμένος AI βοηθός για έναν οδηγό 3D Printing.
    Απάντησε στην ερώτηση του χρήστη βασιζόμενος ΑΠΟΚΛΕΙΣΤΙΚΑ στις παρακάτω πληροφορίες του οδηγού.
    Αν η απάντηση δεν υπάρχει στον οδηγό, πες ευγενικά ότι δεν καλύπτεται ακόμα από την τεκμηρίωση.
    Απάντησε στα Ελληνικά, με φιλικό και κατανοητό ύφος.

    ΠΕΡΙΕΧΟΜΕΝΟ ΟΔΗΓΟΥ:
    {guide_content}

    ΕΡΩΤΗΣΗ ΧΡΗΣΤΗ:
    {user_query}
    """
    reply = ask_gemini(prompt)
    issue.create_comment(reply)
