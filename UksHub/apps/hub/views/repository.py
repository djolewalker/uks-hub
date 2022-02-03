from unicodedata import name
from django.http.response import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from UksHub.apps.events.forms import CommentForm
from UksHub.apps.events.services import event_user_to_artefact

from UksHub.apps.gitcore.services import get_repository
from UksHub.apps.hub.forms import IssueForm, LabelForm
from UksHub.apps.hub.models import Label, Milestone
from UksHub.apps.hub.services import find_branch_from_path, find_repo, generate_hierarchy, get_last_commits, is_user_ssh_enabled
from UksHub.apps.advancedsearch.models import Query
from UksHub.apps.advancedsearch.mapper import map_query_to_filter

_sort_options = [
    ('sort:created-desc', 'Newest'),
    ('sort:created-asc', 'Oldest'),
    ('sort:comments-desc', 'Most commented'),
    ('sort:comments-asc', 'Least commented'),
    ('sort:updated-desc', 'Recently updated'),
    ('sort:updated-asc', 'Least recently updated')
]


def _execute_query(repository, query):
    if query:
        f, s, e, a, m, q = map_query_to_filter(query)

        artefacts = repository.artefact_set.annotate(
            **a
        ).filter(
            *m,
            **f,
        ).exclude(
            **e
        ).order_by(
            *s
        ).all()

    else:
        artefacts = repository.artefact_set.all()
        q = Query()

    queries = {
        'open': q.set_state('is:open'),
        'closed': q.set_state('is:closed'),
        'author': q.clear_author(),
        'assignee': q.clear_assignee(),
        'sort': q.clear_sort()
    }

    return artefacts, q, queries


def tree(request, username, reponame, path=None):
    if request.method == 'GET':
        repo = find_repo(request.user, username, reponame)
        repo_obj = get_repository(repo.creator, repo.name)
        if not repo_obj:
            raise Http404

        ssh_enabled = is_user_ssh_enabled(request.user)

        branch = find_branch_from_path(
            repo_obj, path) if path else repo.default_branch
        branch_obj = next(filter(lambda head: head.name ==
                          branch, repo_obj.branches), None)
        if not branch_obj:
            if repo_obj.heads:
                raise Http404
            return render(request, 'hub/repository/code.html', {
                'repository': repo,
                'repo': repo_obj,
                'ssh_enabled': ssh_enabled})

        path_sections_count = sum([1 for p in path.replace(branch, '')
                                   .split('/') if p]) if path else 0
        hierarchy, tree = generate_hierarchy(branch_obj, path)

        return render(request, 'hub/repository/code.html', {
            'repository': repo,
            'repo': repo_obj,
            'branch': branch,
            'ssh_enabled': ssh_enabled,
            'tree': tree,
            'hierarchy': hierarchy,
            'commit': branch_obj.commit,
            'stats': get_last_commits(repo_obj, branch, tree, path_sections_count)})
    raise Http404


def blob(request, username, reponame, path=None):
    if request.method == 'GET':
        repo = find_repo(request.user, username, reponame)
        repo_obj = get_repository(repo.creator, repo.name)

        branch = find_branch_from_path(
            repo_obj, path) if path else repo.default_branch
        branch_obj = next(filter(lambda head: head.name ==
                          branch, repo_obj.branches), None)
        if not branch_obj:
            if repo_obj.branches:
                raise Http404
            return render(request, 'hub/repository/code.html', {
                'repository': repo,
                'repo': repo_obj,
                'ssh_enabled': is_user_ssh_enabled(request.user)})

        blob = path.replace(f'{branch}/', '')
        if not blob:
            raise Http404

        blob_obj = branch_obj.commit.tree[blob]
        if not blob_obj:
            raise Http404

        commit = next(repo_obj.iter_commits(
            branch, paths=blob, max_count=1), None)
        if not commit:
            raise Http404

        return render(request, 'hub/repository/code.html', {
            'repository': repo,
            'repo': repo_obj,
            'branch': branch,
            'commit': commit,
            'blob': blob_obj,
            'hierarchy': generate_hierarchy(branch_obj, path)[0]})
    raise Http404


def issues(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        default_query = 'is:issue is:open'
        query = request.GET.get('q', default_query)
        artefacts, return_query, binding_queries = _execute_query(
            repository,
            query
        )
        labels = Label.objects.all()
        milestones = Milestone.objects.all()

        return render(request, 'hub/repository/artefacts.html', {
            'repository': repository,
            'artefacts': artefacts,
            'query': str(return_query),
            'queries': binding_queries,
            'ispr': False,
            'is_default_query': query == default_query,
            'sort_options': _sort_options,
            'labelscount': len(labels),
            'milestonescount': len(milestones)
        })

    raise Http404


def issue(request, username, reponame, id):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        issue = repository.artefact_set.get(pk=id)
        if not issue:
            raise Http404
        return render(request, 'hub/repository/issue.html', {'repository': repository, 'issue': issue})
    raise Http404


def create_issue(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        issue_form = IssueForm()
        repository.contributors.add(repository.creator)
        issue_form.fields['assignees'].queryset = repository.contributors
        comment_form = CommentForm()

    elif request.method == 'POST':
        repository = find_repo(request.user, username, reponame)
        issue_form = IssueForm(request.POST)
        comment_form = CommentForm(request.POST)
        if issue_form.is_valid():
            issue = issue_form.save(commit=False)
            issue.repository = repository
            issue.creator = request.user
            issue.save()
            issue_form.save_m2m()

            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.creator = request.user
                comment.artefact = issue
                comment.save()
                issue.message = comment
                issue.save()

            # Create events
            if issue.assignees.all():
                event_user_to_artefact(
                    request.user, issue, issue.assignees.all()
                )

            return redirect(reverse('issue', kwargs={'username': username, 'reponame': reponame, 'id': issue.id}))
    else:
        raise Http404
    return render(request, 'hub/repository/new-issue.html', {'repository': repository, 'issue_form': issue_form, 'comment_form': comment_form})


def pull_requests(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        default_query = 'is:pr is:open'
        query = request.GET.get('q', default_query)
        artefacts, return_query, binding_queries = _execute_query(
            repository,
            query
        )

        return render(request, 'hub/repository/artefacts.html', {
            'repository': repository,
            'artefacts': artefacts,
            'query': str(return_query),
            'queries': binding_queries,
            'ispr': True,
            'is_default_query': query == default_query,
            'sort_options': _sort_options
        })

    raise Http404


def pull_request(request, username, reponame, id):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/pull-request.html', {'repository': repository})

    raise Http404


def create_pull_request(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/new-pull-request.html', {'repository': repository})

    raise Http404


def actions(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/actions.html', {'repository': repository})
    raise Http404


def repository_projects(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/repository-projects.html', {'repository': repository})
    raise Http404


def wiki(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/wiki.html', {'repository': repository})
    raise Http404


def security(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/security.html', {'repository': repository})
    raise Http404


def insights(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/insights.html', {'repository': repository})
    raise Http404


def repository_settings(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        return render(request, 'hub/repository/repository-settings.html', {'repository': repository})
    raise Http404

def labels(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        issue
        labels = Label.objects.all()

        return render(request, 'hub/repository/labels.html', {
            'repository': repository,
            'labels': labels,
            'ispr': False,
            'sort_options': _sort_options
        })

    raise Http404

def create_label(request, username, reponame):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        label_form = LabelForm()

    elif request.method == 'POST':
        repository = find_repo(request.user, username, reponame)
        label_form = LabelForm(request.POST)
        if label_form.is_valid():
            label = label_form.save(commit=False)
            label.save()
            label_form.save_m2m()

            request.method = 'GET'
            return redirect(request, 'hub/repository/labels.html', {'username': username, 'reponame': reponame})
    else:
        raise Http404
    return render(request, 'hub/repository/new-label.html', {'repository': repository, 'label_form': label_form})

def edit_label(request, username, reponame, label_name):
    if request.method == 'GET':
        repository = find_repo(request.user, username, reponame)
        label = Label.objects.get(name=label_name)
        label_form = LabelForm(data={'name':label.name, 'description':label.description, 'color':label.color})

    elif request.method == 'POST':
        repository = find_repo(request.user, username, reponame)
        label_form = LabelForm(request.POST)
        label = Label.objects.get(name=label_name)
        if label_form.is_valid():
            label.name = label_form.data['name']
            label.description = label_form.data['description']
            label.save()

            request.method = 'GET'
            return redirect(request, 'hub/repository/labels.html', {'username': username, 'reponame': reponame})
    else:
        raise Http404
    return render(request, 'hub/repository/edit-label.html', {'repository': repository, 'label_form': label_form})

def remove_label(request, username, reponame, label_name):
    if request.method == 'GET':
        Label.objects.filter(name=label_name).delete()
        return redirect(request, 'hub/repository/labels.html', {'username': username, 'reponame': reponame})