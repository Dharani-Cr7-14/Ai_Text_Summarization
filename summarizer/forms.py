from django import forms

from .models import SummaryHistory


class SummarizationForm(forms.Form):
    summary_length = forms.ChoiceField(
        choices=SummaryHistory.LENGTH_CHOICES,
        initial=SummaryHistory.LENGTH_MEDIUM,
    )
    text = forms.CharField(required=False, widget=forms.Textarea)
    url = forms.URLField(required=False)
    pdf_file = forms.FileField(required=False)

    max_text_length = 25000

    def clean(self):
        cleaned_data = super().clean()
        text = (cleaned_data.get("text") or "").strip()
        url = (cleaned_data.get("url") or "").strip()
        pdf_file = cleaned_data.get("pdf_file")

        provided_sources = [bool(text), bool(url), bool(pdf_file)]
        if sum(provided_sources) != 1:
            raise forms.ValidationError("Provide exactly one input source: text, URL, or PDF.")

        if text and len(text) > self.max_text_length:
            raise forms.ValidationError(
                f"Input text is too long. Limit is {self.max_text_length} characters."
            )

        if pdf_file:
            if not pdf_file.name.lower().endswith(".pdf"):
                raise forms.ValidationError("Uploaded file must be a PDF.")
            if pdf_file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("PDF file is too large. Max size is 10MB.")

        return cleaned_data