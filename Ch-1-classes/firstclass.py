class llms:
    token_size = 100

    def __init__(self, query):
        self.query = query

    def openai(self):
        print(f"I am openai. You asked {self.query}")

    def claude(self):
        print(f"I am claude. You said {self.query}")

    def llama(self):
        print(f"I am llama. You asked {self.query}")

if __name__ == "__main__":

    obj = llms("What is the meaning of life?")
    obj.openai()
    