(() => {
  const page = document.querySelector('.ask-page');
  if (!page) return;
  const form = document.getElementById('chat-form');
  const question = document.getElementById('chat-question');
  const send = document.getElementById('chat-send');
  const transcript = document.getElementById('chat-transcript');
  const errorBox = document.getElementById('chat-error');
  const progress = document.getElementById('chat-progress');
  const clearForm = document.getElementById('chat-clear-form');
  const clearButton = clearForm.querySelector('button');
  const status = page.querySelector('.ask-status');
  const checkButton = page.querySelector('[data-check-connection]');
  const enabled = !question.disabled;
  const image = document.getElementById('chat-image');
  const preview = document.getElementById('chat-photo-preview');
  const removePhoto = document.getElementById('chat-remove-photo');
  const record = document.getElementById('chat-record');
  const audioInput = document.getElementById('chat-audio');
  const uploadVoice = document.getElementById('chat-upload-voice');
  const voiceLanguage = document.getElementById('chat-voice-language');
  const voiceStatus = document.getElementById('chat-voice-status');
  const imageEnabled = !image.disabled;
  const canRecord = Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  let voiceReady = false;
  let recorder = null;
  let media = null;
  let timer = null;
  let previewUrl = null;
  let leaving = false;
  let busy = false;
  document.getElementById('chat-voice-tools').hidden = false;

  function showError(message) {
    errorBox.textContent = message || '';
    errorBox.hidden = !message;
  }

  function setBusy(value, label = 'Thinking… This may take a moment.') {
    busy = value;
    send.disabled = value || !enabled;
    question.disabled = value || !enabled;
    clearButton.disabled = value || !transcript.querySelector('.ask-message');
    progress.hidden = !value;
    progress.textContent = label;
    form.setAttribute('aria-busy', String(value));
    image.disabled = value || !enabled || !imageEnabled;
    removePhoto.disabled = value;
    uploadVoice.disabled = value || !enabled || !voiceReady;
    voiceLanguage.disabled = value || !enabled;
    record.disabled = value || !enabled || !voiceReady || !canRecord;
    page.querySelectorAll('[data-question]').forEach(button => { button.disabled = value || !enabled; });
  }

  function addMessage(role, text, hasImage = false) {
    const article = document.createElement('article');
    article.className = `ask-message ask-message-${role === 'user' ? 'user' : 'assistant'}`;
    const speaker = document.createElement('span');
    speaker.className = 'ask-speaker';
    speaker.textContent = role === 'user' ? 'You' : 'RootLine AI';
    const bubble = document.createElement('div');
    bubble.className = 'ask-bubble';
    bubble.dir = 'auto';
    // Neither model replies nor user text are interpreted as HTML.
    bubble.textContent = text;
    article.append(speaker, bubble);
    if (hasImage) {
      const tag = document.createElement('span');
      tag.className = 'ask-photo-tag';
      tag.textContent = 'Photo attached · not retained';
      article.insertBefore(tag, bubble);
    }
    if (role === 'assistant' && 'speechSynthesis' in window) {
      const listen = document.createElement('button');
      listen.type = 'button';
      listen.className = 'ask-listen';
      listen.textContent = 'Listen';
      article.append(listen);
    }
    transcript.append(article);
    transcript.scrollTop = transcript.scrollHeight;
    return article;
  }

  function renderHistory(messages) {
    transcript.replaceChildren();
    messages.forEach(message => addMessage(message.role, message.content, message.has_image));
    if (!messages.length) {
      const welcome = document.createElement('div');
      welcome.className = 'ask-welcome';
      const heading = document.createElement('h2');
      heading.textContent = 'A fresh start for your questions';
      const text = document.createElement('p');
      text.textContent = 'Ask about your crop, soil or everyday farming in Bangla or English.';
      welcome.append(heading, text);
      transcript.append(welcome);
    }
  }

  async function post(url, data) {
    const response = await fetch(url, {
      method: 'POST', body: data, credentials: 'same-origin',
      headers: {Accept: 'application/json'},
    });
    let result;
    try { result = await response.json(); }
    catch {
      if (response.status === 403) throw new Error('Your form token expired. Refresh this page and try again.');
      throw new Error('The request could not be completed. Refresh the page and try again.');
    }
    if (!response.ok) throw new Error(result.error || 'The request could not be completed.');
    return result;
  }

  async function checkConnection() {
    checkButton.disabled = true;
    status.textContent = 'Checking local AI…';
    status.dataset.state = 'checking';
    try {
      const response = await fetch(page.dataset.statusUrl, {credentials: 'same-origin', headers: {Accept: 'application/json'}});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not check the connection.');
      status.dataset.state = result.ready ? 'ready' : 'offline';
      status.textContent = result.message;
      voiceReady = Boolean(result.voice?.ready);
      voiceStatus.textContent = result.voice?.message || 'Local voice setup could not be checked.';
      if (!canRecord && voiceReady) voiceStatus.textContent += ' Microphone recording is unavailable here; upload a recording instead.';
    } catch {
      status.dataset.state = 'offline';
      status.textContent = 'Connection could not be checked. Refresh or sign in again.';
    } finally { checkButton.disabled = false; if (!busy) setBusy(false); }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    const text = question.value.trim();
    if (!text && !image.files.length) { showError('Type a question first or attach a photo.'); return; }
    const data = new FormData(form);
    data.set('message', text);
    showError('');
    const welcome = transcript.querySelector('.ask-welcome');
    if (welcome) welcome.hidden = true;
    stopSpeaking();
    const pending = addMessage('user', text || 'What can you observe in this farming photo?', Boolean(image.files.length));
    setBusy(true);
    try {
      const result = await post(form.action, data);
      renderHistory(result.messages);
      question.value = '';
      resetPhoto();
      status.dataset.state = 'ready';
      status.textContent = 'Local AI is ready';
    } catch (error) {
      pending.remove();
      if (welcome) welcome.hidden = false;
      showError(error.message);
    } finally {
      setBusy(false);
      question.focus();
    }
  });

  clearForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !window.confirm('Clear your saved conversation?')) return;
    const data = new FormData(clearForm);
    showError('');
    setBusy(true, 'Clearing your history…');
    stopSpeaking();
    try {
      await post(clearForm.action, data);
      renderHistory([]);
    } catch (error) { showError(error.message); }
    finally { setBusy(false); }
  });

  page.querySelectorAll('[data-question]').forEach(button => {
    button.addEventListener('click', () => {
      question.value = button.dataset.question;
      question.focus();
    });
  });

  function resetPhoto() {
    image.value = '';
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    preview.hidden = true;
    preview.querySelector('img').removeAttribute('src');
  }
  image.addEventListener('change', () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    preview.hidden = true;
    const file = image.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      resetPhoto(); showError('Choose a photo smaller than 5 MB.'); return;
    }
    showError('');
    previewUrl = URL.createObjectURL(file);
    preview.querySelector('img').src = previewUrl;
    preview.hidden = false;
  });
  removePhoto.addEventListener('click', resetPhoto);

  async function transcribe(blob, filename) {
    const data = new FormData();
    data.set('csrfmiddlewaretoken', form.querySelector('[name=csrfmiddlewaretoken]').value);
    data.set('audio', blob, filename);
    data.set('language', voiceLanguage.value);
    showError('');
    setBusy(true, 'Transcribing locally… Review the text before sending.');
    try {
      if (blob.size > 8 * 1024 * 1024) throw new Error('Keep the recording below 8 MB and 60 seconds.');
      const result = await post(page.dataset.transcribeUrl, data);
      question.value = [question.value.trim(), result.text].filter(Boolean).join('\n');
      voiceStatus.textContent = 'Review the transcribed question, edit it if needed, then select Send.';
      if (question.value.length > 2000) showError('Your question is over 2,000 characters. Shorten it before sending.');
    } catch (error) { showError(error.message); }
    finally { setBusy(false); audioInput.value = ''; question.focus(); }
  }

  function releaseMicrophone() {
    clearTimeout(timer);
    media?.getTracks().forEach(track => track.stop());
    media = null;
    record.textContent = 'Record question';
    record.setAttribute('aria-pressed', 'false');
  }

  record.addEventListener('click', async () => {
    if (recorder?.state === 'recording') {
      record.disabled = true;
      recorder.stop();
      return;
    }
    if (busy || !canRecord || !voiceReady) return;
    setBusy(true, 'Allow microphone access to record your question…');
    showError('');
    stopSpeaking();
    try {
      media = await navigator.mediaDevices.getUserMedia({audio: true});
      if (leaving) { releaseMicrophone(); return; }
      const chunks = [];
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      recorder = new MediaRecorder(media, mimeType ? {mimeType} : undefined);
      let failed = false;
      recorder.addEventListener('dataavailable', event => { if (event.data.size) chunks.push(event.data); });
      recorder.addEventListener('error', () => { failed = true; releaseMicrophone(); showError('Recording failed. Try again or upload a recording.'); setBusy(false); });
      recorder.addEventListener('stop', () => {
        const type = recorder.mimeType;
        recorder = null;
        releaseMicrophone();
        if (!failed && !leaving) transcribe(new Blob(chunks, {type}), 'question-recording');
      }, {once: true});
      recorder.start();
      record.disabled = false;
      record.textContent = 'Stop recording';
      record.setAttribute('aria-pressed', 'true');
      progress.textContent = 'Recording… Select Stop when finished (55 seconds maximum).';
      timer = setTimeout(() => { if (recorder?.state === 'recording') recorder.stop(); }, 55000);
    } catch (error) {
      releaseMicrophone(); setBusy(false);
      showError(error.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow it in browser settings or upload a recording.' : 'The microphone could not be opened. Use localhost or HTTPS, or upload a recording.');
    }
  });
  uploadVoice.addEventListener('click', () => audioInput.click());
  audioInput.addEventListener('change', () => { if (audioInput.files[0] && !busy) transcribe(audioInput.files[0], audioInput.files[0].name); });

  function stopSpeaking() {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    transcript.querySelectorAll('.ask-listen').forEach(button => { button.textContent = 'Listen'; });
  }
  transcript.querySelectorAll('.ask-listen').forEach(button => { button.hidden = !('speechSynthesis' in window); });
  transcript.addEventListener('click', event => {
    const button = event.target.closest('.ask-listen');
    if (!button) return;
    const stopping = button.textContent === 'Stop listening';
    stopSpeaking();
    if (stopping) return;
    const text = button.closest('.ask-message').querySelector('.ask-bubble').textContent;
    const language = /[\u0980-\u09ff]/.test(text) ? 'bn' : 'en';
    const voice = speechSynthesis.getVoices().find(item => item.localService && item.lang.toLowerCase().startsWith(language));
    if (!voice) { showError(`No local ${language === 'bn' ? 'Bangla' : 'English'} voice is available on this device. You can still read the answer.`); return; }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.onend = utterance.onerror = () => { button.textContent = 'Listen'; };
    button.textContent = 'Stop listening';
    speechSynthesis.speak(utterance);
  });
  window.addEventListener('pagehide', () => { leaving = true; if (recorder?.state === 'recording') recorder.stop(); releaseMicrophone(); stopSpeaking(); });
  checkButton.addEventListener('click', checkConnection);
  if (!question.disabled) checkConnection();
  transcript.scrollTop = transcript.scrollHeight;
})();
