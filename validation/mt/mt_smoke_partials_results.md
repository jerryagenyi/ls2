# MT partial-fragment test — Opus-MT EN->FR (CTranslate2 int8, CPU)

Inputs are deliberately truncated/mid-sentence, mimicking what VAD
chunking feeds the MT stage in the live pipeline (design doc section 8).
Review question for the native speaker: for each row, is the French an
acceptable rendering of the fragment, and does anything get invented,
completed, or garbled that would mislead a listener?

| Type | English fragment | French output |
|------|------------------|---------------|
| truncated-head | Good morning everyone and a | Bonjour tout le monde et un |
| truncated-head | Before we begin I would like to thank the | Avant de commencer, je voudrais remercier |
| truncated-head | The shuttle buses to the hotels leave every | Les navettes vers les hôtels laissent chaque |
| truncated-head | Our target is to raise two million | Notre objectif est de réunir deux millions de personnes. |
| truncated-head | Registration for tomorrow's breakout sessions closes at | L'inscription pour les séances en petits groupes de demain se termine à |
| mid-sentence-start | will now share the findings from the community health survey | partagera maintenant les résultats de l'enquête sur la santé communautaire |
| mid-sentence-start | begins with an appeal to present your bodies as a living sacrifice | commence par un appel à présenter vos corps comme un sacrifice vivant |
| mid-sentence-start | if you need to take a call | si vous avez besoin d'un appel |
| mid-sentence-start | who still needs a name badge or a | qui a encore besoin d'un badge nominatif ou d'un |
| clause-cut | We are delighted to see so many delegates gathered here from every | Nous sommes ravis de voir tant de délégués réunis ici |
| clause-cut | Please check the notice board beside the main entrance to find | Veuillez consulter le tableau d'affichage à côté de l'entrée principale pour trouver |
| clause-cut | Each workshop will run for ninety minutes, with a short | Chaque atelier durera quatre-vingt-dix minutes, avec un court |
| short-utterance | Thank you. | Je vous remercie. |
| short-utterance | Please be seated. | Asseyez-vous. |
| short-utterance | One moment please | Un instant s'il vous plaît. |

Avg latency/fragment: 76 ms (max 121 ms).

