#!/usr/bin/env python

import optparse
import sys
import re
import logging
import getpass
import csv

from datetime import datetime

from github import Github
from github import GithubException

# The minimum number of remaining Github rate-limited API requests before we pre-emptively
# abort to avoid hitting the limit part-way through migrating an issue.

GITHUB_SPARE_REQUESTS = 50

# Mapping between statuses and github bug state

STATUS_MAPPING = {
    'closed' : 'closed',
    'new' : 'open',
    'assigned' : 'open',
    'accepted' : 'open'
}

def github_label(name, color = "FFFFFF"):

    """ Returns the Github label with the given name, creating it if necessary. """

    try: return label_cache[name]
    except KeyError:
        try: return label_cache.setdefault(name, github_repo.get_label(name))
        except GithubException:
            return label_cache.setdefault(name, github_repo.create_label(name, color))

def github_user(name):

    """ Returns the Github user with the given nickname. """

    try: return user_cache[name]
    except KeyError:
        try: return user_cache.setdefault(name, github.get_user(name))
        except GithubException:
            raise ValueError("No such user, " + name)


def convert_to_github(issue):
    # Github rate-limits API requests to 5000 per hour, and if we hit that limit part-way
    # through adding an issue it could end up in an incomplete state.  To avoid this we'll
    # ensure that there are enough requests remaining before we start migrating an issue.

    if github.rate_limiting[0] < GITHUB_SPARE_REQUESTS:
        raise Exception("Aborting to to impending Github API rate-limit cutoff.")

    state = STATUS_MAPPING.get(issue["status"], "open")
    title = issue["summary"]
    body = str(issue)
    creator = issue["reporter"]
    assigned = issue["owner"]
    labels = ["imported"]
    for label_column in ("type", "priority", "component"):
        if issue[label_column]:
            labels.append(label_column.title() + ":" + issue[label_column])
    if issue["keywords"]:
        labels += issue["keywords"].split()
    print "{0} [{1}] Created By: {2} Assigned To: {3} Labels: {4}, Description: {5}".format(title, state, creator, assigned, labels, body)
    if not options.dry_run:
        github_issue = github_repo.create_issue(
            title,
            assignee = github_user(assigned),
            body = body.encode("utf-8"), 
            labels = [github_label(label) for label in labels])
        if state == "closed":
            github_issue.edit(state = "closed")


if __name__ == "__main__":

    usage = "usage: %prog [options] <csv file> <github username> <github project>"
    description = "Migrate all issues from a csv export of a Git repository project to a Github project."
    parser = optparse.OptionParser(usage = usage, description = description)

    parser.add_option("-d", "--dry-run", action = "store_true", dest = "dry_run", help = "Don't modify anything on Github", default = False)

    options, args = parser.parse_args()

    if len(args) != 3:
        parser.print_help()
        sys.exit()

    label_cache = {}    # Cache Github tags, to avoid unnecessary API requests
    user_cache = {}

    csv_file_name, github_user_name, github_project = args
    github_password = getpass.getpass("Github password: ")

    github = Github(github_user_name, github_password)
    current_user = github.get_user()

    if "/" in github_project:
        owner_name, github_project = github_project.split("/")
        try: github_owner = github.get_user(owner_name)
        except GithubException:
            try: github_owner = github.get_organization(owner_name)
            except GithubException:
                github_owner = current_user
    else: github_owner = current_user

    github_repo = github_owner.get_repo(github_project)

    try:
        with open(csv_file_name, 'r') as csv_file:
            git_issues_reader = csv.DictReader(csv_file)
            for issue in git_issues_reader:
                convert_to_github(issue)
    except Exception:
        parser.print_help()
        raise
