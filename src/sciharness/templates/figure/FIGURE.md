# Figure {{FIGURE_ID}}

## Scientific message

What should this figure communicate?

## Evidence basis

Which evidence-bearing experiments or analyses support this figure?

## Panel structure

### Panel A

Purpose:

Evidence source:

Expected visual:

### Panel B

Purpose:

Evidence source:

Expected visual:

## Main / supplementary relationship

...

## Validation requirements

...

## Release criteria

Release requires explicit human approval. After validation, record it with:

```bash
sci figure approve {{FIGURE_ID}} --by "Reviewer Name"
sci figure validate {{FIGURE_ID}} --release
```

Approval records hashes of this file, `manifest.yaml`, every release output,
and paired source data. Editing any of them afterwards invalidates approval.
