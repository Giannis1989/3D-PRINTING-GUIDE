import os
import glob
from github import Github
from google import genai

g = Github(os.environ["GITHUB_TOKEN"])
repo = g.get_repo(os.environ["REPO_NAME"])
issue = repo.get_issue(number=int(os.environ["ISSUE_NUMBER"]))

guide_content = ""
for filepath in glob.glob("**/*.md", recursive=True):
    with open(filepath, "r", encoding="utf-8") as file:
        guide_content += f"\n--- Αρχείο: {filepath} ---\n"
        guide_content += file.read()

comments = list(issue.get_comments())
if comments:
    user_query = comments[-1].body
else:
    user_query = f"{issue.title}\n{issue.body}"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=prompt,
)

issue.create_comment(response.text)
