# AI Text Summarizer

A production-ready Django web app that summarizes long text using HuggingFace Transformers (`facebook/bart-large-cnn`).

## Features

- Text summarization using Transformer model
- Summary length control: Short, Medium, Detailed
- Word statistics: original words, summary words, compression percentage
- Summary history stored in SQLite
- Copy summary button
- Loading spinner during model inference
- Input validation for empty/invalid/oversized input
- Responsive Bootstrap 5 interface
- Advanced features:
  - PDF upload + summarization
  - Website URL extraction + summarization
  - Download summary as `.txt`
  - Dark mode toggle
- REST API endpoint: `POST /api/summarize/`

## Tech Stack

- Backend: Python, Django, Transformers, PyTorch
- Frontend: HTML5, CSS3, Bootstrap 5, JavaScript (AJAX)
- Database: SQLite

## Project Structure

```
text_summarization/
├── text_summarizer/
│   ├── settings.py
│   ├── urls.py
│   └── ...
├── summarizer/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── forms.py
│   ├── summarizer_model.py
│   └── migrations/
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   │   └── styles.css
│   └── js/
│       └── app.js
├── manage.py
├── requirements.txt
├── Procfile
├── Dockerfile
└── README.md
```

## Local Setup

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run migrations:

```bash
python manage.py migrate
```

4. Start server:

```bash
python manage.py runserver
```

5. Open:

```text
http://127.0.0.1:8000/
```

## API Usage

### Endpoint

`POST /api/summarize/`

### JSON Body

```json
{
  "text": "Long text content...",
  "summary_length": "medium"
}
```

`summary_length` values: `short`, `medium`, `detailed`

### cURL Example

```bash
curl -X POST http://127.0.0.1:8000/api/summarize/ \
  -H "Content-Type: application/json" \
  -d '{"text": "Artificial intelligence is transforming industries...", "summary_length": "short"}'
```

## Example Test Inputs

- A long news article paragraph (300+ words)
- A research abstract
- A blog post URL (`https://example.com/article`)
- A PDF report (1-5 pages)

## Production Configuration

Set environment variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=your-domain.onrender.com,localhost,127.0.0.1`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.onrender.com`

## Deployment

### Render

1. Push code to GitHub.
2. Create a new **Web Service** on Render.
3. Set build command:

```bash
pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput
```

4. Set start command:

```bash
gunicorn text_summarizer.wsgi:application --bind 0.0.0.0:$PORT
```

5. Add required environment variables.

### Railway

1. Create project and connect repository.
2. Add environment variables from **Production Configuration**.
3. Railway will use `Procfile` automatically.
4. Ensure migration command runs at deploy time:

```bash
python manage.py migrate
```

### Docker (Optional)

Build image:

```bash
docker build -t ai-text-summarizer .
```

Run container:

```bash
docker run -p 8000:8000 \
  -e DJANGO_SECRET_KEY="change-me" \
  -e DJANGO_DEBUG=False \
  -e DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1" \
  ai-text-summarizer
```

## Notes

- First request may take time while model files are downloaded.
- For large-scale production, switch to PostgreSQL and add background task queues.