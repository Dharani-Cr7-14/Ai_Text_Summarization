import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import SummarizationForm
from .models import SummaryHistory
from .summarizer_model import extract_text_from_pdf, extract_text_from_url, summarize_with_points


def _word_count(text: str) -> int:
	return len([word for word in text.split() if word.strip()])


def _compression_percentage(original_count: int, summary_count: int) -> float:
	if original_count == 0:
		return 0.0
	ratio = (1 - (summary_count / original_count)) * 100
	return round(max(ratio, 0.0), 2)


@require_GET
def index(request):
	history_items = SummaryHistory.objects.all()[:10]
	return render(
		request,
		"index.html",
		{
			"history_items": history_items,
			"summary_lengths": SummaryHistory.LENGTH_CHOICES,
		},
	)


def _resolve_source_text(cleaned_data):
	text = (cleaned_data.get("text") or "").strip()
	url = (cleaned_data.get("url") or "").strip()
	pdf_file = cleaned_data.get("pdf_file")

	if text:
		return SummaryHistory.SOURCE_TEXT, text
	if url:
		extracted = extract_text_from_url(url)
		if not extracted:
			raise ValueError("Could not extract text from the provided URL.")
		return SummaryHistory.SOURCE_URL, extracted
	if pdf_file:
		extracted = extract_text_from_pdf(pdf_file.read())
		if not extracted:
			raise ValueError(
				"Could not extract text from the uploaded PDF. The file may be image-based or scanned; try a text-based PDF."
			)
		return SummaryHistory.SOURCE_PDF, extracted
	raise ValueError("No input text found.")


@require_POST
def summarize_view(request):
	form = SummarizationForm(request.POST, request.FILES)
	if not form.is_valid():
		return JsonResponse({"ok": False, "error": form.errors.as_text()}, status=400)

	summary_length = form.cleaned_data["summary_length"]

	try:
		source_type, source_text = _resolve_source_text(form.cleaned_data)
		result = summarize_with_points(source_text, summary_length)
		summary = result["summary"]
		key_points = result["key_points"]
	except Exception as exc:
		return JsonResponse({"ok": False, "error": str(exc)}, status=400)

	original_word_count = _word_count(source_text)
	summary_word_count = _word_count(summary)
	compression_percentage = _compression_percentage(original_word_count, summary_word_count)

	history = SummaryHistory.objects.create(
		source_type=source_type,
		summary_length=summary_length,
		original_text=source_text,
		generated_summary=summary,
		original_word_count=original_word_count,
		summary_word_count=summary_word_count,
		compression_percentage=compression_percentage,
	)

	return JsonResponse(
		{
			"ok": True,
			"data": {
				"id": history.id,
				"summary": summary,
				"key_points": key_points,
				"original_word_count": original_word_count,
				"summary_word_count": summary_word_count,
				"compression_percentage": compression_percentage,
				"created_at": history.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
			},
		}
	)


@require_POST
@csrf_exempt
def summarize_api(request):
	try:
		payload = json.loads(request.body.decode("utf-8"))
	except json.JSONDecodeError:
		return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)

	form = SummarizationForm(
		{
			"text": payload.get("text", ""),
			"url": payload.get("url", ""),
			"summary_length": payload.get("summary_length", SummaryHistory.LENGTH_MEDIUM),
		}
	)

	if not form.is_valid():
		return JsonResponse({"ok": False, "error": form.errors.as_text()}, status=400)

	summary_length = form.cleaned_data["summary_length"]
	try:
		source_type, source_text = _resolve_source_text(form.cleaned_data)
		result = summarize_with_points(source_text, summary_length)
		summary = result["summary"]
		key_points = result["key_points"]
	except Exception as exc:
		return JsonResponse({"ok": False, "error": str(exc)}, status=400)

	original_word_count = _word_count(source_text)
	summary_word_count = _word_count(summary)
	compression_percentage = _compression_percentage(original_word_count, summary_word_count)

	history = SummaryHistory.objects.create(
		source_type=source_type,
		summary_length=summary_length,
		original_text=source_text,
		generated_summary=summary,
		original_word_count=original_word_count,
		summary_word_count=summary_word_count,
		compression_percentage=compression_percentage,
	)

	return JsonResponse(
		{
			"ok": True,
			"data": {
				"id": history.id,
				"summary": summary,
				"key_points": key_points,
				"original_word_count": original_word_count,
				"summary_word_count": summary_word_count,
				"compression_percentage": compression_percentage,
				"source_type": source_type,
			},
		}
	)


@require_GET
def download_summary(request):
	summary = (request.GET.get("summary") or "").strip()
	if not summary:
		return JsonResponse({"ok": False, "error": "No summary content to download."}, status=400)

	response = HttpResponse(summary, content_type="text/plain; charset=utf-8")
	response["Content-Disposition"] = 'attachment; filename="summary.txt"'
	return response
