import csv
from datetime import datetime

# Read the CSV file
with open('dataset/all_projects_final.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    header = reader.fieldnames
    rows = list(reader)

# Sort by Project (ascending) then by Backport Date (descending)
rows_sorted = sorted(rows, key=lambda x: (x['Project'], x['Backport Date']), reverse=False)
# Custom sort to handle descending dates within each project
from operator import itemgetter
rows_sorted = sorted(rows, key=lambda x: (x['Project'], x['Backport Date']), reverse=False)
rows_sorted_desc = []
current_project = None
project_rows = []
for row in rows_sorted:
    if row['Project'] != current_project:
        if project_rows:
            project_rows.sort(key=lambda x: x['Backport Date'], reverse=True)
            rows_sorted_desc.extend(project_rows)
        current_project = row['Project']
        project_rows = [row]
    else:
        project_rows.append(row)
if project_rows:
    project_rows.sort(key=lambda x: x['Backport Date'], reverse=True)
    rows_sorted_desc.extend(project_rows)
rows_sorted = rows_sorted_desc

# Write back to the same file
with open('dataset/all_projects_final.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows_sorted)

print("File sorted successfully!")
print(f"Total rows: {len(rows_sorted)}")
print("\nFirst few rows after sorting:")
for row in rows_sorted[:10]:
    print(f"{row['Project']} - {row['Backport Date']}")
