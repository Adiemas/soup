# .NET — testing

Tool: xUnit + FluentAssertions + (optionally) NSubstitute / Moq. Coverage via `coverlet.collector`.

## 1. Layout

```
src/
  Soup.Invoices/               # production
  Soup.Invoices.Api/
tests/
  Soup.Invoices.Tests/         # unit
  Soup.Invoices.IntegrationTests/
  Soup.Invoices.Api.Tests/     # WebApplicationFactory
```

1. Test project per production project: `<Project>.Tests` and `<Project>.IntegrationTests`.
2. Mirror namespace layout: `Soup.Invoices.Core.PaymentService` → `Soup.Invoices.Tests.Core.PaymentServiceTests`.
3. One test class per production type.

## 2. Naming

Test method name encodes: Method_State_ExpectedOutcome.

```csharp
public class PaymentServiceTests
{
    [Fact]
    public async Task PayAsync_AmountExceedsBalance_Throws() { ... }

    [Fact]
    public async Task PayAsync_ExactAmount_SettlesInvoice() { ... }
}
```

Alternative (BDD-style) is also acceptable: `Given_When_Then`. Pick one per project and stick with it.

## 3. Arrange / Act / Assert

Always label the three phases with a blank line or a comment when non-trivial:

```csharp
[Fact]
public async Task PayAsync_PartialAmount_LeavesOutstandingBalance()
{
    // Arrange
    var invoice = InvoiceBuilder.New().WithTotal(1_000).Build();
    var sut     = new PaymentService(Repo.Stub(invoice));

    // Act
    var result = await sut.PayAsync(invoice.Id, amountCents: 400, ct: default);

    // Assert
    result.BalanceCents.Should().Be(600);
    result.Status.Should().Be(InvoiceStatus.PartiallyPaid);
}
```

## 4. FluentAssertions

1. Use `.Should()` for every assertion — readable diffs, better failure messages.
2. `.Should().BeEquivalentTo(expected)` for deep equality on DTOs/records.
3. `.Should().ThrowAsync<SomeException>().WithMessage("*contains*")` for exceptions.
4. Prefer explicit `because` messages when an assertion's intent isn't obvious.

## 5. Test data builders

1. Every aggregate in tests has a Builder: `InvoiceBuilder.New().WithTotal(1_000).WithCustomer(c).Build()`.
2. Builders live in `tests/.../Builders/`. They set sensible defaults and expose fluent `With...` methods.
3. Don't new-up entities directly in tests with 10 positional args — it hurts readability and drifts when the schema changes.

```csharp
public sealed class InvoiceBuilder
{
    private Guid _id = Guid.NewGuid();
    private int  _totalCents = 1_000;
    private InvoiceStatus _status = InvoiceStatus.Open;

    public static InvoiceBuilder New() => new();
    public InvoiceBuilder WithTotal(int cents) { _totalCents = cents; return this; }
    public InvoiceBuilder WithStatus(InvoiceStatus s) { _status = s; return this; }
    public Invoice Build() => new(_id, _totalCents, _status);
}
```

## 6. Theories

Use `[Theory]` + `[InlineData]` / `[MemberData]` for parameterized cases. Keep data literal and close to the test:

```csharp
[Theory]
[InlineData(0,     false)]
[InlineData(400,   true )]
[InlineData(1_000, true )]
public void IsValidPayment_Scenarios(int amountCents, bool expected)
    => PaymentPolicy.IsValid(amountCents).Should().Be(expected);
```

For complex data use a `TheoryData<...>` class member to keep type safety.

## 7. Integration tests

1. Use `WebApplicationFactory<TEntryPoint>` for HTTP-level tests; do not spin up Kestrel manually.
2. Replace real externals with `Testcontainers` (Postgres, Redis) — no shared dev DB.
3. Seed through the public API when possible; fall back to `DbContext` only when the API can't express the state.
4. Wrap each test in a transaction that rolls back, or use a `respawn`-style reset between tests.

## 8. Mocking — sparingly

1. Don't mock types you don't own (EF Core's `DbContext`, `HttpClient`). Use a test double or Testcontainers.
2. Mock at the port (`IInvoiceRepository`) — not inside pure domain logic.
3. Never mock value objects or data structures.

## 9. Async tests

1. Tests are `async Task`. Never `async void`.
2. Always flow `CancellationToken` — use `TestContext.Current.CancellationToken` if xUnit v3.
3. No `Thread.Sleep`. Use `TaskCompletionSource` / polling with timeout to await events.

## 10. Coverage

1. `coverlet.collector` in every test csproj.
2. Target ≥80% line coverage per project; ≥90% on core domain assemblies.
3. Exclude generated code via `[ExcludeFromCodeCoverage]` or `coverlet.runsettings`.

## 11. Checklist

- [ ] Tests follow AAA structure
- [ ] Use builders, not positional constructors
- [ ] No shared mutable state between tests
- [ ] All async tests use `Task`, flow `CancellationToken`
- [ ] Integration tests use Testcontainers, not shared DB
