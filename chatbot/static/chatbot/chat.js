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
  let busy = false;

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
    page.querySelectorAll('[data-question]').forEach(button => { button.disabled = value || !enabled; });
  }

  function addMessage(role, text) {
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
    transcript.append(article);
    transcript.scrollTop = transcript.scrollHeight;
    return article;
  }

  function renderHistory(messages) {
    transcript.replaceChildren();
    messages.forEach(message => addMessage(message.role, message.content));
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
    } catch {
      status.dataset.state = 'offline';
      status.textContent = 'Connection could not be checked. Refresh or sign in again.';
    } finally { checkButton.disabled = false; }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    const text = question.value.trim();
    if (!text) { showError('Type a question first.'); return; }
    const data = new FormData(form);
    data.set('message', text);
    showError('');
    const welcome = transcript.querySelector('.ask-welcome');
    if (welcome) welcome.hidden = true;
    const pending = addMessage('user', text);
    setBusy(true);
    try {
      const result = await post(form.action, data);
      renderHistory(result.messages);
      question.value = '';
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
  checkButton.addEventListener('click', checkConnection);
  if (!question.disabled) checkConnection();
  transcript.scrollTop = transcript.scrollHeight;
})();
