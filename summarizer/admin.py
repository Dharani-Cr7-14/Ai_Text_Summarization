from django.contrib import admin

from .models import SummaryHistory


@admin.register(SummaryHistory)
class SummaryHistoryAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"source_type",
		"summary_length",
		"original_word_count",
		"summary_word_count",
		"compression_percentage",
		"created_at",
	)
	list_filter = ("source_type", "summary_length", "created_at")
	search_fields = ("original_text", "generated_summary")

# Register your models here.
