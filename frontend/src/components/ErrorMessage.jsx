export default function ErrorMessage({ message }) {
  return (
    <div className="notice error" role="alert">
      <span className="notice-icon">!</span>
      <span>{message}</span>
    </div>
  );
}
