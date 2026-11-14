"""Common English words that say nothing about a job, left out when keywords are taken from a job
description (the ATS score works for English text)."""

STOPWORDS = frozenset(
    """
    a about above across after again against all also am an and any are as at be because been
    before being below between both but by can could did do does doing down during each either
    etc few for from further had has have having he her here hers him his how i if in into is it
    its just may me might more most must my no nor not now of off on once one only or other our
    ours out over own per same shall she should so some such than that the their theirs them then
    there these they this those through to too under until up upon us very was we were what when
    where which while who whom whose why will with within without would you your yours able
    ability across additional alongside among and/or around available based best build building
    candidate candidates collaborate company concerning day deliver demonstrated desirable
    develop developing drive duties effective ensure environment essential excellent experience
    experienced familiar following good great help high highly include including join key level
    looking make making manage meet need needs new opportunity part passion plus preferred
    provide providing required requirements responsibilities responsible role seeking skills
    strong support team teams time understanding use using various want well work working years
    year
    """.split()
)
