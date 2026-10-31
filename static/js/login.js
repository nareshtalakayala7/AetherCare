document.querySelectorAll('.demo-roles button').forEach((button) => button.addEventListener('click', () => {
  document.querySelector('input[name="email"]').value = button.dataset.email;
  document.querySelector('input[name="password"]').value = button.dataset.password;
  document.querySelector('input[name="email"]').focus();
}));
