from django.db import models


class SummaryHistory(models.Model):
	SOURCE_TEXT = "text"
	SOURCE_PDF = "pdf"
	SOURCE_URL = "url"
	SOURCE_CHOICES = [
		(SOURCE_TEXT, "Text"),
		(SOURCE_PDF, "PDF"),
		(SOURCE_URL, "URL"),
	]

	LENGTH_SHORT = "short"
	LENGTH_MEDIUM = "medium"
	LENGTH_DETAILED = "detailed"
	LENGTH_CHOICES = [
		(LENGTH_SHORT, "Short"),
		(LENGTH_MEDIUM, "Medium"),
		(LENGTH_DETAILED, "Detailed"),
	]

	source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_TEXT)
	summary_length = models.CharField(max_length=10, choices=LENGTH_CHOICES, default=LENGTH_MEDIUM)
	original_text = models.TextField()
	generated_summary = models.TextField()
	original_word_count = models.PositiveIntegerField(default=0)
	summary_word_count = models.PositiveIntegerField(default=0)
	compression_percentage = models.FloatField(default=0.0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"Summary #{self.id} ({self.source_type})"
