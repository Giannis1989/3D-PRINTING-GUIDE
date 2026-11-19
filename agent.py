import os
import glob
import time
from github import Github
from google import genai

g = Github(os.environ["GITHUB_TOKEN"])
repo = g.get_repo(os.environ["REPO_NAME"])
issue = repo.get_issue(number=int(os.environ["ISSUE_NUMBER"]))

files_dict = {}
guide_content = ""
for filepath in glob.glob("**/*.md", recursive=True):
    with open(filepath, "r", encoding="utf-8") as file:
        content = file.read()
        files_dict[filepath] = content
        guide_content += f"\n--- Αρχείο: {filepath} ---\n{content}"

comments = list(issue.get_comments())
user_query = comments[-1].body if comments else f"{issue.title}\n{issue.body}"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

available_models = [
    m.name.replace("models/", "") for m in client.models.list()
    if "gemini" in m.name and not any(x in m.name for x in ["embedding", "imagen", "veo"])
]

def ask_gemini(prompt_text):
    for model_name in available_models:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt_text)
            return res.text
        except Exception:
            continue
    raise RuntimeError("Δεν βρέθηκε ενεργό μοντέλο.")

if user_query.strip().startswith("/add"):
    task = user_query.replace("/add", "", 1).strip()
    prompt = f"""
    Είσαι συντάκτης ενός κορυφαίου οδηγού 3D Printing στα Ελληνικά.
    Ο διαχειριστής σου ζητά να προσθέσεις νέο περιεχόμενο στον οδηγό: "{task}"
    
    Διάβασε τα υπάρχοντα αρχεία του οδηγού:
    {guide_content}
    
    Απάντησε ΑΥΣΤΗΡΑ με την εξής μορφή:
    FILE: <ακριβές όνομα υπάρχοντος αρχείου .md ή νέου αρχείου .md>
    CONTENT:
    <ολόκληρο το ενημερωμένο περιεχόμενο του αρχείου σε καθαρό Markdown χωρίς ```markdown στην αρχή/τέλος>
    """
    result = ask_gemini(prompt).strip()
    
    header, new_content = result.split("CONTENT:", 1)
    target_file = header.replace("FILE:", "").strip()
    new_content = new_content.strip()
    
    branch_name = f"ai-update-{issue.number}-{int(time.time())}"
    main_ref = repo.get_git_ref("heads/main")
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=main_ref.object.sha)
    
    if target_file in files_dict:
        existing_file = repo.get_contents(target_file, ref="main")
        repo.update_file(target_file, f"AI προσθήκη περιεχομένου (#{issue.number})", new_content, existing_file.sha, branch=branch_name)
    else:
        repo.create_file(target_file, f"AI νέο αρχείο (#{issue.number})", new_content, branch=branch_name)
        
    pr = repo.create_pull(title=f"AI Προσθήκη: {task[:50]}", body=f"Αυτόματη πρόταση από το Issue #{issue.number}", head=branch_name, base="main")
    issue.create_comment(f"Ετοίμασα το νέο περιεχόμενο στο αρχείο `{target_file}`! Μπορείς να το ελέγξεις και να το εγκρίνεις (Merge) εδώ: {pr.html_url}")

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
