import { expect, type Page } from "@playwright/test"

const apiUrl = process.env.VITE_API_URL ?? "http://localhost:8000"

export async function signUpNewUser(
  page: Page,
  name: string,
  email: string,
  password: string,
) {
  await page.goto("/signup")

  await page.getByTestId("full-name-input").fill(name)
  await page.getByTestId("email-input").fill(email)
  await page.getByTestId("password-input").fill(password)
  await page.getByTestId("confirm-password-input").fill(password)
  await page.getByRole("button", { name: "Sign Up" }).click()
  await page.goto("/login")
}

export async function logInUser(page: Page, email: string, password: string) {
  // The browser login form intentionally uses the administrator-only endpoint.
  // Legacy feature tests still need a normal user session, so obtain the regular
  // API token directly instead of weakening the production login boundary.
  const response = await page.request.post(
    `${apiUrl}/api/v1/login/access-token`,
    {
      form: {
        username: email,
        password,
      },
    },
  )
  expect(response.ok()).toBeTruthy()
  const payload = (await response.json()) as { access_token: string }

  await page.goto("/login")
  await page.evaluate((token) => {
    localStorage.setItem("access_token", token)
  }, payload.access_token)
  await page.goto("/")
  await expect(
    page.getByText("Welcome back, nice to see you again!"),
  ).toBeVisible()
}

export async function logOutUser(page: Page) {
  await page.getByTestId("user-menu").click()
  await page.getByRole("menuitem", { name: "Log out" }).click()
  await page.goto("/login")
}
