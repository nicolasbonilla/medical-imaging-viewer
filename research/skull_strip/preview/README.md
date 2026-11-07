# Private test address (not production)

Hosting only: no Firestore or Storage rules, so it cannot change production settings. Deploy ONLY to a preview channel:

    firebase hosting:channel:deploy ai-test --config research/skull_strip/preview/firebase.preview.json --project brain-mri-476110 --expires 7d

Its COOP/COEP headers (cross-origin isolation, 8 threads) are not in the production `firebase.json` yet: speeds measured here are not what production gets.
