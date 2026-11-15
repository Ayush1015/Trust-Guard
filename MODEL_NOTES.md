# Model and data notes

## What this update includes

Application source and test/training harnesses. It does not add new model binaries, tokenizers, raw datasets, runtime databases or compiled frontend assets. Existing artifacts/data are unchanged from the earlier repository. Their presence does not establish permission to redistribute them.

The code prefers v2 local classifiers, with v1 fallback, and optionally loads local ONNX source-stance files from `TrustGuard/ml-service/models/nli/`. Without that folder, NLI is unavailable and the service must report it as unavailable. A fresh clone is not the same profile as the separate local demo bundle.

## Provenance recorded during development

- Local NLI: `cross-encoder/nli-MiniLM2-L6-H768`, recorded as Apache-2.0. Requires a quantized ONNX export, tokenizer and config, not included here. Source stance is text comparison, not a fact check.
- Phishing v2 training: PhiUSIIL Phishing URL Dataset, UCI dataset 967, recorded as CC BY 4.0, plus presumed-legitimate public URLs. Preserve dataset attribution and inspect its current terms before use. Presumed legitimacy is a weak label, not an independent safety check.
- Review v2 training: Salminen et al. (2022) Fake Reviews corpus, upstream OSF `osf.io/tyue9`, recorded as CC BY 4.0, via `theArijitDas/Fake-Reviews-Dataset`; and `Flowerly/modern-fake-reviews`, recorded as CC BY 4.0. The mirror records Apache-2.0 processing. Preserve original attribution. The task labels distinguish generated from human-written text, not deceptive from truthful reviews.
- News v2: derived from the pre-existing Kaggle news CSV. Exact original corpus and license are unresolved. Do not redistribute the dataset or derived weights without resolving permission. Random-split scores on this corpus are not real-world accuracy.
- The pre-existing `cleaned_cybersecurity.csv` also has unresolved source/license documentation.

These records are provenance leads, not a blanket license for the whole project or all derived artifacts. Check upstream terms before redistribution or commercial use. `training/bootstrap_nli.py` downloads hash-checked NLI files; `training/fetch_datasets.py` fetches review/phishing datasets. Training scripts use repository-relative paths with TG_* overrides. News data must be supplied separately with checked permission. They remain development harnesses, not exact reproduction of the local demo model bundle.

## Optional runtime downloads

`HF_NEWS_MODELS` is configurable. Development defaults referenced:

- `ThomasTschinkel/fake-news-detector`: recorded as MIT.
- `akanbrown/AI-Fake_News_Detection_Roberta`: recorded as MIT.
- `d-mistry013/fake-news-detector`: no stated license found during review.
- `dhruvpal/fake-news-bert`: no stated license found during review.

No copies of these runtime-downloaded models are added by this update. Download availability is not license permission. Review model cards and licenses, especially the two unresolved entries. Set `ENABLE_HF_NEWS_MODELS=false` to disable these downloads; doing so changes the model profile.

BERTPhish is disabled by default and requires separately supplied local files. No BERTPhish model is bundled.

Only load trusted joblib/pickle artifacts: deserialization can execute code. Keep API keys outside the repository and client/extension code.
