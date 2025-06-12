from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
import os
from io import StringIO, BytesIO
import uuid
import logging
import sys

app = Flask(__name__)
app.secret_key = str(uuid.uuid4())
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

# Configure logging to both console and file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Create uploads folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER)
        logger.info(f"Created uploads folder: {UPLOAD_FOLDER}")
    except Exception as e:
        logger.error(f"Failed to create uploads folder: {str(e)}")
        raise

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    try:
        uploaded_files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if allowed_file(f)]
        logger.info(f"Found {len(uploaded_files)} files in uploads folder: {uploaded_files}")
    except Exception as e:
        logger.error(f"Error listing files in uploads folder: {str(e)}")
        uploaded_files = []
        flash(f"Error accessing uploads folder: {str(e)}")
    return render_template('index.html', uploaded_files=uploaded_files)

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        flash('No files selected')
        logger.warning("No files selected in upload request")
        return redirect(url_for('index'))

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        flash('No files selected')
        logger.warning("Empty or invalid file selection")
        return redirect(url_for('index'))

    saved_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                # Check file size before saving
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)  # Reset file pointer
                if file_size == 0:
                    flash(f'File {filename} is empty')
                    logger.warning(f"Empty file uploaded: {filename}")
                    continue
                if file_size > app.config['MAX_CONTENT_LENGTH']:
                    flash(f'File {filename} exceeds size limit (50 MB)')
                    logger.warning(f"Oversized file: {filename} ({file_size} bytes)")
                    continue

                # Save file
                file.save(file_path)
                if os.path.exists(file_path):
                    # Verify file is not empty and readable
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        if not content:
                            os.remove(file_path)
                            flash(f'File {filename} is empty or invalid')
                            logger.warning(f"Empty or invalid file saved: {file_path}")
                            continue
                    saved_files.append(filename)
                    logger.info(f"Saved file: {file_path} ({file_size} bytes)")
                else:
                    flash(f'Failed to save {filename}: File not found after saving')
                    logger.error(f"File not found after saving: {file_path}")
            except Exception as e:
                flash(f'Failed to save {filename}: {str(e)}')
                logger.error(f"Failed to save {filename}: {str(e)}")
        else:
            flash(f'Invalid file: {file.filename}. Only CSV files are allowed.')
            logger.warning(f"Invalid file uploaded: {file.filename}")

    if saved_files:
        flash(f'Successfully uploaded {len(saved_files)} file(s)')
    else:
        flash('No files were successfully uploaded')
    return redirect(url_for('index'))

@app.route('/remove/<filename>', methods=['POST'])
def remove_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            flash(f'Removed {filename}')
            logger.info(f"Removed file: {file_path}")
        except Exception as e:
            flash(f'Failed to remove {filename}: {str(e)}')
            logger.error(f"Failed to remove {filename}: {str(e)}")
    else:
        flash(f'File {filename} not found')
        logger.warning(f"File not found for removal: {file_path}")
    return redirect(url_for('index'))

@app.route('/combine', methods=['POST'])
def combine_csv():
    try:
        uploaded_files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if allowed_file(f)]
        logger.info(f"Combining {len(uploaded_files)} files: {uploaded_files}")
    except Exception as e:
        flash(f'Error accessing uploads folder: {str(e)}')
        logger.error(f"Error accessing uploads folder: {str(e)}")
        return redirect(url_for('index'))

    if not uploaded_files:
        flash('No CSV files found in uploads folder')
        logger.warning("No CSV files found in uploads folder")
        return redirect(url_for('index'))

    valid_files = []
    for filename in uploaded_files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            valid_files.append(file_path)
        else:
            flash(f'File {filename} not found')
            logger.error(f"File not found: {file_path}")
            return redirect(url_for('index'))

    try:
        dfs = []
        headers = None
        for file_path in valid_files:
            try:
                # Open file in binary mode and use BytesIO
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                    if not file_content:
                        flash(f'File {os.path.basename(file_path)} is empty')
                        logger.warning(f"Empty file: {file_path}")
                        continue
                    df = pd.read_csv(BytesIO(file_content), dtype=str, keep_default_na=False, encoding='utf-8')
                if df.empty:
                    flash(f'File {os.path.basename(file_path)} is empty or invalid')
                    logger.warning(f"Empty or invalid CSV: {file_path}")
                    continue
                if headers is None:
                    headers = list(df.columns)
                elif list(df.columns) != headers:
                    flash('Header mismatch detected. All CSV files must have identical headers.')
                    logger.error(f"Header mismatch in {file_path}")
                    return redirect(url_for('index'))
                dfs.append(df)
                logger.info(f"Successfully read {file_path}")
            except Exception as e:
                flash(f'Error reading {os.path.basename(file_path)}: {str(e)}')
                logger.error(f"Error reading {file_path}: {str(e)}")
                return redirect(url_for('index'))

        if not dfs:
            flash('No valid CSV files could be read')
            logger.warning("No valid CSV files could be read")
            return redirect(url_for('index'))

        combined_df = pd.concat(dfs, ignore_index=True)
        output = StringIO()
        combined_df.to_csv(output, index=False, encoding='utf-8')
        csv_bytes = output.getvalue().encode('utf-8')  # Encode text to bytes
        output_bytes = BytesIO(csv_bytes)
        output_bytes.seek(0)

        # Delete files after successful combining
        for file_path in valid_files:
            try:
                os.remove(file_path)
                logger.info(f"Deleted file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {str(e)}")

        return send_file(
            output_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name='combined_output.csv'
        )

    except Exception as e:
        flash(f'Error combining files: {str(e)}')
        logger.error(f"Error combining files: {str(e)}")
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)