from tools.web_ops import browse_url

def main():
    res = browse_url("https://github.com/bytedance/deer-flow")
    print(res)

if __name__ == "__main__":
    main()
