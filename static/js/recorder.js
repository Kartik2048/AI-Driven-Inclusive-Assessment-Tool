let mediaRecorder;
let audioChunks = [];

document.getElementById('startRecord').addEventListener('click', async () => {
    audioChunks = [];
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    
    mediaRecorder.ondataavailable = (event) => {
        audioChunks.push(event.data);
    };
    
    mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        const formData = new FormData();
        formData.append('audio', audioBlob);
        formData.append('reference', document.getElementById('reference-text').textContent);
        
        const response = await fetch('/speaking', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        location.reload(); // Refresh to show results
    };
    
    mediaRecorder.start();
    document.getElementById('startRecord').disabled = true;
    document.getElementById('stopRecord').disabled = false;
    document.getElementById('recordingStatus').textContent = '🔴 Recording...';
});

document.getElementById('stopRecord').addEventListener('click', () => {
    mediaRecorder.stop();
    document.getElementById('startRecord').disabled = false;
    document.getElementById('stopRecord').disabled = true;
    document.getElementById('recordingStatus').textContent = 'Processing...';
});
