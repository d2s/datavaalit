import json
import time

from django.template import RequestContext
from django.shortcuts import render_to_response
from social.models import *
from political.models import *
from political.api import *
from geo.models import Municipality
from django.core.urlresolvers import reverse
from django.core.mail import mail_admins
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.db.models import Count
from django.core.cache import cache

def show_candidates_social_feeds(request):
    tw = {}
    tw['feed_count'] = CandidateFeed.objects.filter(type="TW").count()
    tw['update_count'] = Update.objects.filter(feed__type="TW").count()
    fb = {}
    fb['feed_count'] = CandidateFeed.objects.filter(type="FB").count()
    fb['update_count'] = Update.objects.filter(feed__type="FB").count()
    last_update = CandidateFeed.objects.filter(last_update__isnull=False).order_by('-last_update')[0].last_update
    args = dict(tw=tw, fb=fb, last_update=last_update)
    return render_to_response('political/candidate_social_feeds.html', args,
                              context_instance=RequestContext(request))

def candidate_change_request(request):
    muni_list = []
    for muni in Municipality.objects.all():
        muni_list.append((muni.id, muni.name))

    args = dict(muni_json=json.dumps(muni_list, ensure_ascii=False))
    return render_to_response('political/candidate_change_request.html', args,
                              context_instance=RequestContext(request))

def _calc_submission_history(election, muni=None):
    budget_list = CampaignBudget.objects.filter(candidate__election=election)
    if muni:
        budget_list = budget_list.filter(candidate__municipality=muni)
    party_list = []
    for p in Party.objects.all():
        d = {'id': p.pk, 'name': p.name, 'code': p.code, 'disclosure_data': []}
        cand_list = Candidate.objects.filter(election=election, party=p)
        if muni:
            cand_list.filter(municipality=muni)
        d['num_candidates'] = cand_list.count()
        party_list.append(d)

    timestamps = budget_list.order_by('time_submitted').values_list('time_submitted', flat=True).distinct()
    for ts in timestamps:
        ts_epoch = int(time.mktime(ts.timetuple()) * 1000)
        for p in party_list:
            nr_submitted = budget_list.filter(candidate__party=p['id'], time_submitted__lte=ts).count()
            p['disclosure_data'].append((ts_epoch, nr_submitted))

    return json.dumps(party_list, ensure_ascii=False)


def _calc_prebudget_stats():
    args = {}
    election = Election.objects.get(year=2012, type='muni')
    # Find the list of candidates that have submitted the campaign prebudgets
    submitted_list = CampaignBudget.objects.filter(advance=True, candidate__election=election)
    muni_list = Municipality.objects.annotate(num_candidates=Count('candidate')).filter(num_candidates__gt=0).order_by('name')
    muni_dict = {}

    for muni in muni_list:
        muni_dict[muni.pk] = muni
        muni.num_submitted = 0

    # Calculate how many candidates have submitted the budgets per muni.
    # Also figure out when the candidate first submitted the advance disclosure.
    for budget in submitted_list:
        muni = muni_dict[budget.candidate.municipality_id]
        muni.num_submitted += 1

    muni_dict = {}
    for muni in muni_list:
        m = {'num_submitted': muni.num_submitted,
             'num_candidates': muni.num_candidates}
        muni_dict[muni.pk] = m
    args['muni_json'] = json.dumps(muni_dict, indent=None)
    args['party_json'] = _calc_submission_history(election)

    return args

def show_prebudget_stats(request):
    # The calculation takes a bit of time, so cache the results.
    args = cache.get('prebudget_stats')
    if not args:
        args = _calc_prebudget_stats()
        cache.set('prebudget_stats', args, 3600)
    return render_to_response('political/candidate_budgets.html', args,
                              context_instance=RequestContext(request))

def candidate_change_request_form(request):
    if request.method == 'GET':
        return render_to_response('political/candidate_change_request_ok.html',
                                  context_instance=RequestContext(request))
    args = request.POST
    try:
        cand_id = int(args['candidate-id'])
        request_str = args['request']
    except:
        return HttpResponseRedirect(reverse('political.views.candidate_change_request'))
    try:
        cand = Candidate.objects.get(pk=cand_id)
    except Candidate.DoesNotExist:
        return HttpResponseRedirect(reverse('political.views.candidate_change_request'))

    subject = "Change request: %s" % unicode(cand)
    message = """
Info
----
"""
    message += "Candidate: %s\n" % unicode(cand)
    message += "Request:\n%s" % unicode(request_str)

    mail_admins(subject, message, fail_silently=False)

    return HttpResponseRedirect(reverse('political.views.candidate_change_request_form'))

