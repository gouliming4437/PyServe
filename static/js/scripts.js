document.addEventListener('keydown', function(e) {
    // Alt + H = Home
    if (e.altKey && e.key === 'h') {
        window.location.href = '/';
    }
    // Alt + S = Search focus
    if (e.altKey && e.key === 's') {
        document.querySelector('.search-bar input').focus();
    }
}); 